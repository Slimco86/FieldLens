"""Bounded, SSRF-safe visual-reference research for the S5 designer (WELLBORE_ASSET_GENERATION 6).

Only equipment name/model hints leave the application (a short query string); nothing else from a
project is sent. The search backend is pluggable and OFF by default (:class:`OffSearchBackend`);
tests use fakes and no default code path touches the network.

Safety properties (AG-9):

* only ``http``/``https`` on ports 80/443, no credentials in the URL;
* every host is resolved and ALL addresses must be public (no private, loopback, link-local,
  multicast, reserved or metadata addresses); the connection goes to the validated address (DNS
  rebinding safe) and every redirect hop is validated again;
* only URLs returned by the search backend are fetched (a URL read from a document or from a page is
  never followed), size, time and redirect caps apply, and only HTML/text pages and small PNG/JPEG/WebP images are accepted;
* hard limits on queries, pages and wall-clock time per component, repeated queries/URLs stop the
  loop, and the result is an explicit found / not found outcome;
* page content is untrusted data: it is never given to the model as instructions and never
  executed; only a sanitised title and a short note are stored.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urljoin, urlsplit

import httpx

from fieldlens.contracts.asset_spec import IMAGE_CONTENT_TYPES, MAX_IMAGE_BYTES

DEFAULT_MAX_QUERIES = 6
DEFAULT_MAX_PAGES = 10
DEFAULT_DEADLINE_S = 120.0
MAX_PAGE_BYTES = 512 * 1024
MAX_REDIRECTS = 3
FETCH_TIMEOUT_S = 10.0
ALLOWED_PORTS = (80, 443)
TEXT_TYPES = ("text/html", "text/plain", "application/xhtml+xml")
LABEL = "External visual reference, not evidence of installation."
_HINT_OK = re.compile(r"[^\w\s/.\-+]", re.UNICODE)


class UrlRejected(ValueError):
    """A URL failed the SSRF/allowlist checks (stable, non-sensitive message)."""


@dataclass(frozen=True)
class SearchHit:
    url: str
    title: str = ""
    snippet: str = ""


class SearchBackend(Protocol):
    @property
    def enabled(self) -> bool: ...

    def search(self, query: str, max_results: int) -> list[SearchHit]: ...


class OffSearchBackend:
    """Default: research is off, no query is made and no component gets a reference."""

    enabled = False

    def search(self, query: str, max_results: int) -> list[SearchHit]:
        return []


@dataclass(frozen=True)
class FetchedPage:
    url: str
    content_type: str
    text: str = ""
    image: bytes | None = None


class PageFetcher(Protocol):
    def fetch(self, url: str) -> FetchedPage: ...


Resolver = Callable[[str, int], list[str]]


def system_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({str(i[4][0]) for i in infos})


def _public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%")[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def check_url(url: str, resolver: Resolver = system_resolver) -> tuple[str, int, str, list[str]]:
    """Validate ``url``; returns (host, port, scheme, public addresses). Raises UrlRejected."""
    if not isinstance(url, str) or len(url) > 2048 or any(ord(c) < 33 for c in url):
        raise UrlRejected("url is malformed")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise UrlRejected("scheme not allowed")
    if parts.username or parts.password:
        raise UrlRejected("credentials in url")
    host = parts.hostname
    if not host or host.casefold() == "localhost" or host.endswith((".local", ".internal")):
        raise UrlRejected("host not allowed")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise UrlRejected("port invalid") from exc
    if port not in ALLOWED_PORTS:
        raise UrlRejected("port not allowed")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    try:
        addresses = [str(literal)] if literal is not None else resolver(host, port)
    except OSError as exc:
        raise UrlRejected("host does not resolve") from exc
    if not addresses or not all(_public(a) for a in addresses):
        raise UrlRejected("address not public")
    return host, port, parts.scheme, addresses


class SafeHttpFetcher:
    """GET with the checks above. ``transport`` is injectable for tests (no real network)."""

    def __init__(
        self,
        resolver: Resolver = system_resolver,
        transport: httpx.BaseTransport | None = None,
        timeout_s: float = FETCH_TIMEOUT_S,
    ) -> None:
        self._resolver = resolver
        self._transport = transport
        self._timeout = timeout_s

    def fetch(self, url: str) -> FetchedPage:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            host, port, scheme, addrs = check_url(current, self._resolver)
            pinned = urlsplit(current)._replace(
                netloc=f"[{addrs[0]}]:{port}" if ":" in addrs[0] else f"{addrs[0]}:{port}"
            )
            with httpx.Client(
                transport=self._transport,
                timeout=self._timeout,
                follow_redirects=False,
                trust_env=False,
                verify=True,
            ) as client:
                with client.stream(
                    "GET",
                    pinned.geturl(),
                    headers={
                        "Host": host,
                        "User-Agent": "FieldLens-visual-reference/1",
                        "Accept": "text/html,image/png,image/jpeg,image/webp;q=0.8",
                    },
                    extensions={"sni_hostname": host},
                ) as resp:
                    if resp.status_code in (301, 302, 303, 307, 308):
                        loc = resp.headers.get("location")
                        if not loc:
                            raise UrlRejected("redirect without location")
                        current = urljoin(current, loc)
                        continue
                    if resp.status_code != 200:
                        raise UrlRejected(f"http status {resp.status_code}")
                    ctype = resp.headers.get("content-type", "").split(";")[0].strip().casefold()
                    is_image = ctype in IMAGE_CONTENT_TYPES
                    if not is_image and ctype not in TEXT_TYPES:
                        raise UrlRejected("content type not allowed")
                    cap = MAX_IMAGE_BYTES if is_image else MAX_PAGE_BYTES
                    body = bytearray()
                    for chunk in resp.iter_bytes():
                        body.extend(chunk)
                        if len(body) > cap:
                            raise UrlRejected("response too large")
                    if is_image:
                        return FetchedPage(current, ctype, image=bytes(body))
                    return FetchedPage(current, ctype, text=bytes(body).decode("utf-8", "replace"))
        raise UrlRejected("too many redirects")


class ImageSink(Protocol):
    def store(self, content_type: str, data: bytes) -> dict[str, Any]: ...


class FileImageSink:
    """Content-addressed image files under ``<root>/visual-references`` (reference, not bytes in
    the spec)."""

    def __init__(self, root: Path) -> None:
        self._dir = root / "visual-references"

    def store(self, content_type: str, data: bytes) -> dict[str, Any]:
        if content_type not in IMAGE_CONTENT_TYPES or not 0 < len(data) <= MAX_IMAGE_BYTES:
            raise UrlRejected("image not allowed")
        digest = hashlib.sha256(data).hexdigest()
        self._dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = self._dir / digest
        if not target.exists():
            tmp = self._dir / f".{digest}.tmp"
            tmp.write_bytes(data)
            tmp.replace(target)
        return {
            "storage_key": f"visual-references/{digest}",
            "content_type": content_type,
            "size_bytes": len(data),
            "sha256": digest,
        }


@dataclass(frozen=True)
class ResearchLimits:
    max_queries: int = DEFAULT_MAX_QUERIES
    max_pages: int = DEFAULT_MAX_PAGES
    deadline_s: float = DEFAULT_DEADLINE_S


@dataclass
class ResearchResult:
    found: bool
    reason: (
        str  # found | not_found | disabled | limit_queries | limit_pages | limit_time | cancelled
    )
    reference: dict[str, Any] | None = None
    queries: int = 0
    pages: int = 0
    rejected: list[str] = field(default_factory=list)


def clean_text(value: str, limit: int) -> str:
    """Printable, single-line, bounded text from untrusted content."""
    kept = "".join(" " if unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp") else c for c in value)
    return " ".join(kept.split())[:limit]


def clean_hint(value: str) -> str:
    return " ".join(_HINT_OK.sub(" ", value).split())[:80]


def _title(html: str) -> str:
    found = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return clean_text(re.sub(r"<[^>]+>", " ", found.group(1)), 200) if found else ""


def _tokens(hint: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{3,}", hint.casefold())}


class VisualReferenceResearcher:
    """``research(hint, kind)``: at most ``limits`` queries/pages/seconds, explicit outcome."""

    def __init__(
        self,
        backend: SearchBackend,
        fetcher: PageFetcher,
        limits: ResearchLimits | None = None,
        image_sink: ImageSink | None = None,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        resolver: Resolver = system_resolver,
    ) -> None:
        self._resolver = resolver
        self._backend = backend
        self._fetcher = fetcher
        self.limits = limits or ResearchLimits()
        self._sink = image_sink
        self._clock = clock
        self._now = now

    @property
    def enabled(self) -> bool:
        return self._backend.enabled

    def research(
        self, hint: str, kind: str, cancelled: Callable[[], bool] = lambda: False
    ) -> ResearchResult:
        lim = self.limits
        text = clean_hint(hint)
        if not self._backend.enabled or not text:
            return ResearchResult(False, "disabled" if not self._backend.enabled else "not_found")
        deadline = self._clock() + lim.deadline_s
        result = ResearchResult(False, "not_found")
        seen_q: set[str] = set()
        seen_u: set[str] = set()
        want = _tokens(text)
        spoken = kind.replace("_", " ")
        for query in (f"{text} {spoken}", text, f"{text} {spoken} datasheet photo"):
            norm = query.casefold()
            if norm in seen_q:
                continue  # a repeated query is never sent twice
            if result.queries >= lim.max_queries:
                result.reason = "limit_queries"
                return result
            if cancelled():
                result.reason = "cancelled"
                return result
            if self._clock() >= deadline:
                result.reason = "limit_time"
                return result
            seen_q.add(norm)
            result.queries += 1
            try:
                hits = self._backend.search(query, 5)
            except Exception:  # noqa: BLE001 - a failing backend is "not found", never a crash
                result.reason = "not_found"
                continue
            fresh = [h for h in hits if h.url not in seen_u][:5]
            if not fresh:
                continue  # nothing new: the next (different) query or stop
            for hit in fresh:
                seen_u.add(hit.url)
                if result.pages >= lim.max_pages:
                    result.reason = "limit_pages"
                    return result
                if cancelled():
                    result.reason = "cancelled"
                    return result
                if self._clock() >= deadline:
                    result.reason = "limit_time"
                    return result
                try:
                    check_url(
                        hit.url, self._resolver
                    )  # allowlist: only search results, only public hosts
                except UrlRejected as exc:
                    result.rejected.append(str(exc))
                    continue
                result.pages += 1
                try:
                    page = self._fetcher.fetch(hit.url)
                except UrlRejected as exc:
                    result.rejected.append(str(exc))
                    continue
                except Exception:  # noqa: BLE001
                    result.rejected.append("fetch failed")
                    continue
                ref = self._reference(hit, page, want)
                if ref is not None:
                    result.found, result.reason, result.reference = True, "found", ref
                    return result
        return result

    def _reference(
        self, hit: SearchHit, page: FetchedPage, want: set[str]
    ) -> dict[str, Any] | None:
        title = clean_text(hit.title, 200) or _title(page.text)
        haystack = f"{title} {hit.snippet} {page.text[:20_000]}".casefold()
        if want and not any(t in haystack for t in want):
            return None  # page does not mention the equipment: not a reference
        ref: dict[str, Any] = {
            "url": hit.url,
            "title": title or None,
            "retrieved_at": self._now().isoformat(),
            "note": f"{LABEL} {clean_text(hit.snippet, 300)}".strip()[:600],
        }
        if page.image is not None and self._sink is not None:
            try:
                ref["image"] = self._sink.store(page.content_type, page.image)
            except UrlRejected:
                pass
        return ref
