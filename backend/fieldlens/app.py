"""FastAPI application factory. Nothing here touches the database at import time."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import RequestResponseEndpoint

from fieldlens import __version__, security
from fieldlens.config import Settings, get_settings
from fieldlens.contracts.errors import ContractError, ErrorBody, ErrorCode, ErrorEnvelope
from fieldlens.contracts.registry import export_component_schemas
from fieldlens.contracts.system import HealthResponse, ReadinessResponse, SessionResponse
from fieldlens.evidence.storage import BlobStore
from fieldlens.ingestion import build_ingestion_router
from fieldlens.jobs import JobWorker, build_jobs_router
from fieldlens.persistence.readiness import evaluate_readiness
from fieldlens.persistence.session import create_db_engine, create_session_factory
from fieldlens.projects import build_projects_router

_STATUS_CODES: dict[int, ErrorCode] = {
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    409: ErrorCode.CONFLICT,
    413: ErrorCode.PAYLOAD_TOO_LARGE,
    415: ErrorCode.UNSUPPORTED_MEDIA_TYPE,
    422: ErrorCode.VALIDATION_ERROR,
    429: ErrorCode.CAPACITY_PAUSED,
    503: ErrorCode.SERVICE_UNAVAILABLE,
}
logger = logging.getLogger(__name__)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or uuid.uuid4().hex


def error_response(
    request: Request,
    status_code: int,
    code: ErrorCode,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    request_id = _request_id(request)
    envelope = ErrorEnvelope(
        error=ErrorBody(code=code, message=message, request_id=request_id, details=details)
    )
    return JSONResponse(
        envelope.model_dump(mode="json"),
        status_code=status_code,
        headers={
            "Cache-Control": "no-store",
            "X-Request-ID": request_id,
            "X-Content-Type-Options": "nosniff",
        },
    )


def require_mutation(request: Request) -> None:
    """Dependency for every state-changing route: Host/Origin/fetch-site + session token."""
    security.check_mutation(request, request.app.state.settings, request.app.state.session_token)


def _register_errors(app: FastAPI) -> None:
    @app.exception_handler(ContractError)
    async def _contract(request: Request, exc: ContractError) -> JSONResponse:
        return error_response(request, exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Never echo submitted input: it may hold source text or secrets.
        issues = [
            {"loc": [str(p) for p in e["loc"]], "type": e["type"], "message": e["msg"]}
            for e in exc.errors()
        ]
        return error_response(
            request,
            422,
            ErrorCode.VALIDATION_ERROR,
            "request failed validation",
            {"errors": issues},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> Response:
        if exc.status_code == 404:
            fallback = _spa_response(request)
            if fallback is not None:
                return fallback
        code = _STATUS_CODES.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        message = exc.detail if isinstance(exc.detail, str) else code.value
        return error_response(request, exc.status_code, code, message)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled %s (request_id=%s)", type(exc).__name__, _request_id(request))
        return error_response(request, 500, ErrorCode.INTERNAL_ERROR, "internal error")


def _build_system_router() -> APIRouter:
    router = APIRouter()

    def health(response: Response) -> HealthResponse:
        response.headers["Cache-Control"] = "no-store"
        return HealthResponse(status="ok", version=__version__)

    def ready(request: Request) -> Response:
        checks = evaluate_readiness(request.app.state.engine)
        if all(c.ok for c in checks):
            body = ReadinessResponse(status="ready", checks=checks)
            return JSONResponse(body.model_dump(mode="json"), headers={"Cache-Control": "no-store"})
        return error_response(
            request,
            503,
            ErrorCode.NOT_READY,
            "service is not ready",
            {"checks": [c.model_dump(mode="json") for c in checks]},
        )

    def session(request: Request) -> Response:
        security.check_session_bootstrap(request, request.app.state.settings)
        body = SessionResponse(csrf_token=request.app.state.session_token)
        return JSONResponse(body.model_dump(mode="json"), headers={"Cache-Control": "no-store"})

    not_ready: dict[int | str, dict[str, Any]] = {
        503: {"model": ErrorEnvelope, "description": "Not ready"}
    }
    for prefix in ("", "/api/v1"):
        router.add_api_route(f"{prefix}/health", health, methods=["GET"], tags=["system"])
        router.add_api_route(
            f"{prefix}/ready",
            ready,
            methods=["GET"],
            response_model=ReadinessResponse,
            responses=not_ready,
            tags=["system"],
        )
    router.add_api_route(
        "/api/v1/session",
        session,
        methods=["GET"],
        response_model=SessionResponse,
        responses={403: {"model": ErrorEnvelope}},
        tags=["system"],
    )
    return router


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    """Serve the production build. SPA fallback happens only for GET/HEAD 404s outside /api/."""
    index = dist / "index.html"
    app.state.spa = (dist.resolve(), index) if index.is_file() else None
    if app.state.spa is not None and (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")


def _spa_response(request: Request) -> Response | None:
    spa = request.app.state.spa
    path = request.url.path
    if spa is None or request.method not in ("GET", "HEAD"):
        return None
    if path == "/api" or path.startswith("/api/") or path.startswith("/assets/"):
        return None
    root, index = spa
    candidate = (root / path.lstrip("/")).resolve()
    if path != "/" and candidate.is_file() and candidate.is_relative_to(root):
        return FileResponse(candidate)
    return FileResponse(index, headers={"Cache-Control": "no-cache"})


def create_app(settings: Settings | None = None, *, session_token: str | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine = create_db_engine(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        worker = app.state.job_worker
        if worker is not None and settings.job_worker_enabled:
            worker.start()
        yield
        if worker is not None:
            worker.stop()
        if engine is not None:
            engine.dispose()

    app = FastAPI(
        title="FieldLens API",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine) if engine is not None else None
    app.state.session_token = session_token or security.new_session_token()
    app.state.blob_store = BlobStore(settings.storage_root)
    app.state.job_worker = (
        JobWorker(app.state.session_factory, app.state.blob_store, settings)
        if app.state.session_factory is not None
        else None
    )

    @app.middleware("http")
    async def boundary(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.request_id = uuid.uuid4().hex
        try:
            security.check_host(request, settings)
        except ContractError as exc:
            response: Response = error_response(request, exc.status_code, exc.code, exc.message)
        else:
            response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        return response

    _register_errors(app)
    app.include_router(_build_system_router())
    app.include_router(build_projects_router())
    app.include_router(build_ingestion_router())
    app.include_router(build_jobs_router())

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
            schema.setdefault("components", {}).setdefault("schemas", {}).update(
                export_component_schemas()
            )
            schema["components"]["schemas"] = dict(sorted(schema["components"]["schemas"].items()))
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]
    _mount_frontend(app, settings.frontend_dist)
    return app


__all__ = ["create_app", "error_response", "require_mutation"]
