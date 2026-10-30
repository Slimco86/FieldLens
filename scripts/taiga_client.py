"""Minimal Taiga REST client (stdlib ``urllib``) with an injectable transport.

Used by ``scripts/track.py sync``. The auth token lives in memory only; every error message is
redacted of credentials. Retries: 429/5xx with ``Retry-After``/backoff (max 4 tries; POST only on
429/503 so a half-processed create is not repeated), one re-authentication on 401.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from typing import Any

API_PATH = "/api/v1"
DEFAULT_URL = "https://api.taiga.io"
TIMEOUT = 20.0
MAX_TRIES = 4
MAX_RETRY_AFTER = 30.0
LOOPBACK = ("127.0.0.1", "localhost", "[::1]")

# transport(method, url, headers, body, timeout) -> (status, response headers, response bytes)
Transport = Callable[
    [str, str, Mapping[str, str], bytes | None, float], tuple[int, dict[str, str], bytes]
]
Sleep = Callable[[float], None]


class TaigaError(Exception):
    """Transport/API failure. The message is already redacted. ``status`` 0 = network."""

    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


def urllib_transport(
    method: str, url: str, headers: Mapping[str, str], body: bytes | None, timeout: float
) -> tuple[int, dict[str, str], bytes]:
    if not url.startswith(("https://", "http://")):
        raise TaigaError("url must be http(s)")
    request = urllib.request.Request(url, data=body, method=method, headers=dict(headers))  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.status, dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers.items()), exc.read()


def _forms(secret: str) -> set[str]:
    return {secret, urllib.parse.quote(secret, safe=""), json.dumps(secret)[1:-1]}


class TaigaClient:
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        *,
        transport: Transport = urllib_transport,
        sleep: Sleep = time.sleep,
        timeout: float = TIMEOUT,
        secrets: Sequence[str] = (),
    ) -> None:
        parsed = urllib.parse.urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise TaigaError("TAIGA_URL must be an http(s) URL")
        if parsed.scheme == "http" and parsed.hostname not in LOOPBACK:
            raise TaigaError("TAIGA_URL must use https (http only for loopback)")
        self._api = base_url.rstrip("/") + API_PATH
        self._username = username
        self._password = password
        self._transport = transport
        self._sleep = sleep
        self._timeout = timeout
        self._secrets = [s for s in (username, password, *secrets) if s]
        self._token: str | None = None
        self.write_calls = 0

    # ------------------------------------------------------------------ plumbing

    def redact(self, text: str) -> str:
        forms: set[str] = set()
        for secret in self._secrets:
            forms |= _forms(secret)
        if self._token:
            forms |= _forms(self._token)
        for form in sorted(forms, key=len, reverse=True):
            text = text.replace(form, "[redacted]")
        return text

    def _once(
        self, method: str, path: str, query: Mapping[str, str] | None, body: Any, auth: bool
    ) -> tuple[int, dict[str, str], bytes]:
        url = self._api + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        headers = {"Accept": "application/json", "x-disable-pagination": "True"}
        data: bytes | None = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if auth and self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return self._transport(method, url, headers, data, self._timeout)

    def _fail(self, status: int, raw: bytes, what: str) -> TaigaError:
        detail = ""
        try:
            payload = json.loads(raw.decode("utf-8"))
            if isinstance(payload, dict):
                detail = json.dumps(payload, sort_keys=True)[:300]
        except ValueError:
            pass
        return TaigaError(self.redact(f"{what}: HTTP {status} {detail}".strip()), status)

    def _delay(self, headers: Mapping[str, str], attempt: int) -> float:
        for key, value in headers.items():
            if key.lower() == "retry-after":
                try:
                    return max(0.0, min(float(value), MAX_RETRY_AFTER))
                except ValueError:
                    break
        return float(min(2**attempt, 8))

    def request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, str] | None = None,
        body: Any = None,
        auth: bool = True,
    ) -> Any:
        if auth and self._token is None:
            self.login()
        is_write = method != "GET"
        if is_write and auth:
            self.write_calls += 1
        retry_statuses = {429, 503} if method == "POST" else {429, 500, 502, 503, 504}
        reauthed = False
        what = f"{method} {path}"
        attempt = 0
        while True:
            attempt += 1
            try:
                status, headers, raw = self._once(method, path, query, body, auth)
            except TaigaError:
                raise
            except Exception as exc:  # noqa: BLE001 - never leak URLs/credentials from tracebacks
                if method == "POST" or attempt >= MAX_TRIES:
                    raise TaigaError(self.redact(f"{what}: {type(exc).__name__}")) from None
                self._sleep(self._delay({}, attempt))
                continue
            if status == 401 and auth and not reauthed:
                reauthed = True
                attempt -= 1
                self._token = None
                self.login()
                continue
            if status in retry_statuses and attempt < MAX_TRIES:
                self._sleep(self._delay(headers, attempt))
                continue
            if status >= 400:
                raise self._fail(status, raw, what)
            if not raw:
                return None
            try:
                return json.loads(raw.decode("utf-8"))
            except ValueError:
                raise TaigaError(f"{what}: response is not JSON", status) from None

    def login(self) -> None:
        self._token = None
        payload = self.request(
            "POST",
            "/auth",
            body={"type": "normal", "username": self._username, "password": self._password},
            auth=False,
        )
        token = payload.get("auth_token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            raise TaigaError("POST /auth: no auth_token in response")
        self._token = token

    # ------------------------------------------------------------------ resources

    def _list(self, path: str, project: int) -> list[dict[str, Any]]:
        data = self.request("GET", path, query={"project": str(project)})
        if not isinstance(data, list):
            raise TaigaError(f"GET {path}: expected a list")
        return [d for d in data if isinstance(d, dict)]

    def me(self) -> dict[str, Any]:
        data = self.request("GET", "/users/me")
        if not isinstance(data, dict):
            raise TaigaError("GET /users/me: unexpected response")
        return data

    def project_by_slug(self, slug: str) -> dict[str, Any]:
        data = self.request("GET", "/projects/by_slug", query={"slug": slug})
        if not isinstance(data, dict) or not isinstance(data.get("id"), int):
            raise TaigaError("GET /projects/by_slug: unexpected response")
        return data

    def story_statuses(self, project: int) -> list[dict[str, Any]]:
        return self._list("/userstory-statuses", project)

    def task_statuses(self, project: int) -> list[dict[str, Any]]:
        return self._list("/task-statuses", project)

    def milestones(self, project: int) -> list[dict[str, Any]]:
        return self._list("/milestones", project)

    def memberships(self, project: int) -> list[dict[str, Any]]:
        return self._list("/memberships", project)

    def userstories(self, project: int) -> list[dict[str, Any]]:
        return self._list("/userstories", project)

    def tasks(self, project: int) -> list[dict[str, Any]]:
        return self._list("/tasks", project)

    def get_object(self, kind: str, object_id: int) -> dict[str, Any]:
        data = self.request("GET", f"/{kind}/{object_id}")
        if not isinstance(data, dict):
            raise TaigaError(f"GET /{kind}/{object_id}: unexpected response")
        return data

    def create(self, kind: str, fields: Mapping[str, Any]) -> dict[str, Any]:
        """``kind`` is ``userstories`` or ``tasks``."""
        data = self.request("POST", f"/{kind}", body=dict(fields))
        if not isinstance(data, dict) or not isinstance(data.get("id"), int):
            raise TaigaError(f"POST /{kind}: unexpected response")
        return data

    def patch(
        self, kind: str, object_id: int, version: int, fields: Mapping[str, Any]
    ) -> dict[str, Any]:
        body = {**fields, "version": version}
        data = self.request("PATCH", f"/{kind}/{object_id}", body=body)
        if not isinstance(data, dict) or not isinstance(data.get("version"), int):
            raise TaigaError(f"PATCH /{kind}/{object_id}: unexpected response")
        return data
