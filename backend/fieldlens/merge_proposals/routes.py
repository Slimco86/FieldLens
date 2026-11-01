"""Merge-proposal routes. Runs need a configured proposer (none in the default app) and
``confirm: true``; decisions are explicit user mutations."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.exc import OperationalError

from fieldlens import security
from fieldlens.contracts.errors import ContractError, ErrorCode, ErrorEnvelope
from fieldlens.contracts.merge_proposals import (
    MergeDecisionRequest,
    MergeProposal,
    MergeProposalEstimate,
    MergeProposalPage,
    MergeProposalRun,
    MergeProposalRunPage,
    MergeProposalStatus,
    MergeRunRequest,
)
from fieldlens.persistence.session import session_scope

from . import service


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


def _proposer(request: Request) -> Any:
    proposer = getattr(request.app.state, "merge_proposer", None)
    if proposer is None:
        raise ContractError(
            ErrorCode.SERVICE_UNAVAILABLE,
            "no model provider is configured for merge proposals",
            503,
            {"reason": "provider_unavailable"},
        )
    return proposer


def build_merge_proposals_router() -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/projects/{project_id}/merge-proposals",
        tags=["merge-proposals"],
        responses={
            404: {"model": ErrorEnvelope},
            409: {"model": ErrorEnvelope},
            503: {"model": ErrorEnvelope},
        },
        dependencies=[Depends(_no_store)],
    )

    @router.get("", response_model=MergeProposalPage)
    def list_proposals(
        project_id: UUID,
        request: Request,
        status: MergeProposalStatus | None = None,
        limit: int = 50,
    ) -> MergeProposalPage:
        limit = max(1, min(limit, 200))
        value = status.value if status is not None else None
        out: MergeProposalPage = _db(
            request, lambda s: service.list_proposals(s, project_id, value, limit)
        )
        return out

    @router.get("/runs", response_model=MergeProposalRunPage)
    def list_runs(project_id: UUID, request: Request) -> MergeProposalRunPage:
        out: MergeProposalRunPage = _db(request, lambda s: service.list_runs(s, project_id))
        return out

    @router.post(
        "/estimate", response_model=MergeProposalEstimate, dependencies=[Depends(_guard_mutation)]
    )
    def estimate(project_id: UUID, request: Request) -> MergeProposalEstimate:
        _db(request, lambda s: service.require_project(s, project_id))
        out: MergeProposalEstimate = _proposer(request).estimate(project_id)
        return out

    @router.post("/runs", response_model=MergeProposalRun, dependencies=[Depends(_guard_mutation)])
    def start_run(project_id: UUID, body: MergeRunRequest, request: Request) -> MergeProposalRun:
        if not body.confirm:
            raise ContractError(
                ErrorCode.VALIDATION_ERROR,
                "confirm the estimate before a model run",
                422,
                {"reason": "confirmation_required"},
            )
        proposer = _proposer(request)
        _db(request, lambda s: service.require_project(s, project_id))
        out: MergeProposalRun = proposer.run(project_id)
        return out

    @router.get("/{proposal_id}", response_model=MergeProposal)
    def get_one(project_id: UUID, proposal_id: UUID, request: Request) -> MergeProposal:
        out: MergeProposal = _db(
            request, lambda s: service.get_proposal(s, project_id, proposal_id)
        )
        return out

    def _decision(name: str) -> Any:
        fn = getattr(service, name)

        def handler(
            project_id: UUID, proposal_id: UUID, body: MergeDecisionRequest, request: Request
        ) -> MergeProposal:
            out: MergeProposal = _db(
                request,
                lambda s: fn(s, project_id, proposal_id, body.decided_by, body.note),
            )
            return out

        handler.__name__ = name
        return handler

    for action in ("accept", "reject", "revert"):
        router.add_api_route(
            f"/{{proposal_id}}/{action}",
            _decision(action),
            methods=["POST"],
            response_model=MergeProposal,
            dependencies=[Depends(_guard_mutation)],
        )
    return router
