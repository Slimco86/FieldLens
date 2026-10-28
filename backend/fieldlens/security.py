"""Local boundary: Host/Origin allowlists, fetch metadata and the per-process mutation token.

There is no multi-user login. A random per-process token plus Host/Origin checks stops other
web origins (and DNS rebinding) from mutating the local API. The token is never logged, placed
in a URL or written to static output.
"""

from __future__ import annotations

import hmac
import secrets

from fastapi import Request

from fieldlens.config import Settings
from fieldlens.contracts.errors import ContractError, ErrorCode

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
TOKEN_HEADER = "X-FieldLens-Token"
TOKEN_BYTES = 32


def new_session_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def check_host(request: Request, settings: Settings) -> None:
    host = (request.headers.get("host") or "").lower()
    if host not in {h.lower() for h in settings.allowed_hosts}:
        raise ContractError(ErrorCode.FORBIDDEN_HOST, "request Host is not allowed", 403)


def check_origin(request: Request, settings: Settings) -> None:
    """Origin, when sent, must be allowlisted. Local CLI/test clients may send none."""
    origin = request.headers.get("origin")
    if origin is not None and origin.lower() not in {o.lower() for o in settings.allowed_origins}:
        raise ContractError(ErrorCode.FORBIDDEN_ORIGIN, "request Origin is not allowed", 403)


def check_fetch_site(request: Request) -> None:
    """Reject browser-declared cross-site requests (``same-site`` is then limited by Origin)."""
    if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
        raise ContractError(ErrorCode.FORBIDDEN_FETCH_SITE, "cross-site requests are refused", 403)


def check_session_bootstrap(request: Request, settings: Settings) -> None:
    check_host(request, settings)
    check_fetch_site(request)
    check_origin(request, settings)


def check_mutation(request: Request, settings: Settings, expected_token: str) -> None:
    """Full guard for state-changing requests; call before any write."""
    check_host(request, settings)
    check_fetch_site(request)
    check_origin(request, settings)
    supplied = request.headers.get(TOKEN_HEADER, "")
    if not supplied or not hmac.compare_digest(supplied.encode(), expected_token.encode()):
        raise ContractError(
            ErrorCode.SESSION_TOKEN_INVALID,
            "missing or stale session token; bootstrap a new session",
            403,
        )
