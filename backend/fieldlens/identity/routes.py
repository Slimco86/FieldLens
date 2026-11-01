"""Project-scoped identity routes: read listing/evidence, explicit (idempotent) re-resolution."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.exc import OperationalError

from fieldlens import security
from fieldlens.contracts.errors import ContractError, ErrorCode, ErrorEnvelope
from fieldlens.contracts.exposure import ProjectExposure, StartGate
from fieldlens.contracts.well_identity import (
    IdentityListing,
    IdentityResolveOutcome,
    WellboreEvidence,
)
from fieldlens.exposure import service as exposure_service
from fieldlens.persistence.session import session_scope

from . import service
from .resolver import resolve_project


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _guard_mutation(request: Request) -> None:
    security.check_mutation(request, request.app.state.settings, request.app.state.session_token)


def _db(request: Request, fn: Any) -> Any:
    factory = request.app.state.session_factory
    if factory is None:
        raise ContractError(ErrorCode.SERVICE_UNAVAILABLE, "storage is unavailable; try again", 503)
    try:
        with session_scope(factory) as session:
            return fn(session)
    except OperationalError as exc:
        raise ContractError(
            ErrorCode.SERVICE_UNAVAILABLE, "storage is unavailable; try again", 503
        ) from exc


def build_identity_router() -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/projects/{project_id}/identity",
        tags=["identity"],
        responses={404: {"model": ErrorEnvelope}, 503: {"model": ErrorEnvelope}},
        dependencies=[Depends(_no_store)],
    )

    @router.get("", response_model=IdentityListing)
    def get_listing(project_id: UUID, request: Request) -> IdentityListing:
        out: IdentityListing = _db(request, lambda s: service.listing(s, project_id))
        return out

    @router.get("/exposure", response_model=ProjectExposure)
    def get_exposure(project_id: UUID, request: Request) -> ProjectExposure:
        out: ProjectExposure = _db(
            request, lambda s: exposure_service.project_exposure(s, project_id)
        )
        return out

    @router.get("/start-gate", response_model=StartGate)
    def get_start_gate(project_id: UUID, request: Request) -> StartGate:
        out: StartGate = _db(request, lambda s: exposure_service.start_gate(s, project_id))
        return out

    @router.get("/wellbores/{wellbore_id}/evidence", response_model=WellboreEvidence)
    def get_evidence(project_id: UUID, wellbore_id: UUID, request: Request) -> WellboreEvidence:
        out: WellboreEvidence = _db(
            request, lambda s: service.wellbore_evidence(s, project_id, wellbore_id)
        )
        return out

    @router.post(
        "/resolve", response_model=IdentityResolveOutcome, dependencies=[Depends(_guard_mutation)]
    )
    def resolve(project_id: UUID, request: Request) -> IdentityResolveOutcome:
        def work(session: Any) -> IdentityResolveOutcome:
            service.require_project(session, project_id)
            r = resolve_project(session, project_id)
            return IdentityResolveOutcome(
                wells=r.wells,
                wellbores=r.wellbores,
                linked_records=r.linked_records,
                unresolved_records=r.unresolved_records,
                identity_findings=r.identity_findings,
                range_findings=r.range_findings,
            )

        out: IdentityResolveOutcome = _db(request, work)
        return out

    return router
