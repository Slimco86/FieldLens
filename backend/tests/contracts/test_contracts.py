"""SC-1..SC-6 contract tests (synthetic fixtures only; no source-data/provider claim)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError

from fieldlens.app import create_app
from fieldlens.contracts import export_component_schemas, public_models
from fieldlens.contracts.base import ContractModel
from fieldlens.contracts.context import (
    AsOf,
    DayAsOf,
    DraftContext,
    EvidenceContext,
    InstantAsOf,
    NumericWindowParams,
    PageParams,
    QueryContext,
    SourceContext,
    SourceEventTime,
    context_cache_key,
    require_context_kind,
    require_same_project,
)
from fieldlens.contracts.errors import ContractError, ErrorCode
from fieldlens.contracts.evidence import (
    Claim,
    ClaimValue,
    Coverage,
    EvidenceClass,
    Locator,
    Quantity,
    ValidationState,
)
from fieldlens.contracts.quality import QualityIssue
from tests.conftest import settings_for

U = uuid.UUID
NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)


def uid() -> uuid.UUID:
    return uuid.uuid4()


def roundtrip(model: type[ContractModel], data: dict[str, Any]) -> ContractModel:
    first = model.model_validate(data)
    again = model.model_validate_json(first.model_dump_json())
    assert again == first
    assert json.loads(first.model_dump_json()) == json.loads(again.model_dump_json())
    return again


# --- SC-1 -----------------------------------------------------------------------------------


def locators(doc: uuid.UUID, rev: uuid.UUID) -> list[dict[str, Any]]:
    base = {"document_id": str(doc), "source_revision_id": str(rev)}
    sha = "f" * 64
    return [
        base
        | {
            "kind": "pdf",
            "page": 3,
            "table_id": "t1",
            "cell_id": "B2",
            "rect": [0.1, 0.2, 0.5, 0.6],
        },
        base | {"kind": "xlsx", "sheet": "Perf", "cell_range": "A1:C9"},
        base
        | {
            "kind": "xml",
            "namespace_uri": "urn:x",
            "element_path": "/a/b[1]",
            "source_uids": ["u1"],
            "attribute_name": "uid",
        },
        base
        | {
            "kind": "text",
            "line_start": 4,
            "line_end": 9,
            "logical_record": 2,
            "column_name": "MD",
            "las_section": "~A",
            "las_mnemonic": "DEPT",
            "las_data_line": 7,
        },
        base
        | {
            "kind": "converted_text",
            "artifact_id": str(uid()),
            "artifact_sha256": sha,
            "extractor_version": "1.0",
            "line_start": 1,
            "line_end": 2,
        },
        base
        | {
            "kind": "embedded_image",
            "container_item_index": 0,
            "image_sha256": sha,
            "region": [0.0, 0.0, 1.0, 1.0],
        },
        {"kind": "derivation", "result_id": str(uid()), "input_claim_ids": [str(uid())]},
    ]


def test_contract_roundtrip_locators_keep_ids_and_positions() -> None:
    doc, rev = uid(), uid()
    adapter = TypeAdapter(Locator)
    for raw in locators(doc, rev):
        parsed = adapter.validate_python(raw)
        again = adapter.validate_json(adapter.dump_json(parsed))
        assert adapter.dump_python(again, mode="json") == raw | {
            k: v for k, v in adapter.dump_python(again, mode="json").items() if k not in raw
        }
        assert again == parsed


def test_contract_roundtrip_claim_quantity_and_time_precision() -> None:
    q = Quantity(
        value=7.0,
        unit="in",
        reference="nominal",
        original_text='7"',
        normalized_value=0.1778,
        normalized_unit="m",
        conversion_validated=True,
    )
    claim = Claim(
        claim_id=uid(),
        project_id=uid(),
        revision_id=uid(),
        subject_id=uid(),
        subject_type="component",
        attribute_key="installed.outside_diameter",
        value=ClaimValue.model_validate({"kind": "quantity", "quantity": q.model_dump()}),
        source_record_ids=[uid()],
        evidence_class=EvidenceClass.SOURCE_RECORD,
    )
    assert Claim.model_validate_json(claim.model_dump_json()) == claim
    assert claim.validation_state is ValidationState.UNREVIEWED

    t = SourceEventTime(
        literal="1999-03",
        precision="month",
        timezone=None,
        earliest_effective=datetime(1999, 3, 1, tzinfo=timezone(timedelta(hours=1))),
        latest_effective=datetime(1999, 3, 31, 23, tzinfo=UTC),
    )
    again = SourceEventTime.model_validate_json(t.model_dump_json())
    assert again == t and again.timezone is None  # unknown zone is preserved, not defaulted
    assert again.earliest_effective == datetime(1999, 2, 28, 23, tzinfo=UTC)  # normalized to UTC


def test_contract_roundtrip_quality_issue_with_all_evidence() -> None:
    doc, rev, proj = uid(), uid(), uid()
    issue = QualityIssue.model_validate(
        {
            "issue_id": str(uid()),
            "context": {"kind": "source", "project_id": str(proj), "source_revision_id": str(rev)},
            "code": "EXTRACTION_PARTIAL",
            "severity": "warning",
            "message": "page 4 unreadable",
            "record_ids": [str(uid())],
            "attribute_keys": ["installed.depth"],
            "evidence_links": [
                {
                    "document_id": str(doc),
                    "source_revision_id": str(rev),
                    "locator": locators(doc, rev)[0],
                }
            ],
            "coverage": {
                "status": "partial",
                "unit": "page",
                "inspected": 3,
                "total": 4,
                "missing_ranges": ["4"],
                "reasons": ["scan too faint"],
            },
            "blocked_operations": ["calculation"],
            "producer_name": "synthetic",
            "producer_version": "0",
            "producer_key": "k1",
            "created_at": "2026-10-28T12:00:00+00:00",
        }
    )
    assert QualityIssue.model_validate_json(issue.model_dump_json()) == issue


def test_openapi_exports_every_public_dto_and_is_deterministic() -> None:
    app = create_app(settings_for(database_url=None))
    schemas = app.openapi()["components"]["schemas"]
    for model in public_models():
        assert model.__name__ in schemas, model.__name__
    assert list(schemas) == sorted(schemas)
    assert json.dumps(export_component_schemas()) == json.dumps(export_component_schemas())
    assert {"EvidenceContext", "Locator", "ClaimValue", "AsOf", "ErrorEnvelope"} <= set(schemas)


def test_registry_complete() -> None:
    names = {m.__name__ for m in public_models()}
    assert {"Project", "QualityIssue", "Claim", "ErrorEnvelope", "SessionResponse"} <= names
    assert "ContractModel" not in names


# --- SC-2 (contract half; DB scope covered in test_migration_roundtrip) ------------------------------


def test_context_project_must_match_path_project() -> None:
    p = uid()
    ctx = EvidenceContext.model_validate(
        {"kind": "source", "project_id": str(p), "source_revision_id": str(uid())}
    )
    require_same_project(p, ctx)
    with pytest.raises(ContractError) as err:
        require_same_project(uid(), ctx)
    assert err.value.status_code == 404  # out-of-context is indistinguishable from absent


def test_source_issue_cannot_reference_other_revision_or_accepted_claims() -> None:
    proj, rev, doc = uid(), uid(), uid()
    base: dict[str, Any] = {
        "issue_id": str(uid()),
        "context": {"kind": "source", "project_id": str(proj), "source_revision_id": str(rev)},
        "code": "UNSUPPORTED_FORMAT",
        "severity": "info",
        "message": "m",
        "producer_name": "p",
        "producer_version": "1",
        "producer_key": "k",
        "created_at": "2026-10-28T12:00:00Z",
    }
    with pytest.raises(ValidationError):
        QualityIssue.model_validate(base | {"claim_ids": [str(uid())]})
    other = {
        "document_id": str(doc),
        "source_revision_id": str(uid()),
        "locator": locators(doc, rev)[1] | {"source_revision_id": str(uid())},
    }
    with pytest.raises(ValidationError):
        QualityIssue.model_validate(base | {"evidence_links": [other]})


# --- SC-3 ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_floats_rejected(bad: float) -> None:
    with pytest.raises(ValidationError):
        Quantity(value=bad, unit="m")
    with pytest.raises(ValidationError):
        NumericWindowParams(start=0, end=bad)
    with pytest.raises(ValidationError):
        Quantity.model_validate_json('{"value": NaN, "unit": "m"}')


def test_unknown_quantity_is_null_with_reason_never_zero() -> None:
    with pytest.raises(ValidationError):
        Quantity()  # no value and no reason
    q = Quantity(unknown_reason="not stated in source")
    assert q.value is None and q.normalized_value is None
    with pytest.raises(ValidationError):
        Quantity(value=0.0)  # known value needs its original unit
    with pytest.raises(ValidationError):
        Quantity(value=1.0, unit="m", normalized_value=1.0, normalized_unit="m")  # unvalidated


def test_invalid_enums_and_unknown_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        Coverage(status="mostly")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Coverage.model_validate({"status": "unknown", "surprise": 1})
    with pytest.raises(ValidationError):
        TypeAdapter(AsOf).validate_python(
            {"kind": "day", "day": "2026-10-28", "timezone": "Mars/Base"}
        )
    with pytest.raises(ValidationError):
        TypeAdapter(AsOf).validate_python(
            {"kind": "instant", "instant": "2026-10-28T12:00:00"}
        )  # no offset
    with pytest.raises(ValidationError):
        Coverage(status="complete", unit="page", inspected=3, total=4)


def test_api_returns_422_with_stable_code_and_no_input_echo() -> None:
    app = create_app(settings_for(database_url=None))

    @app.post("/api/v1/_probe/validate")
    def probe(body: Coverage) -> dict[str, str]:
        return {"ok": "yes"}

    c = TestClient(app, base_url="http://127.0.0.1:8101")
    for payload in (
        '{"status":"complete","reasons":["leak-me"],"extra":1}',
        '{"status":"bogus","reasons":["leak-me"]}',
        '{"status":"unknown","inspected":NaN,"reasons":["leak-me"]}',
    ):
        r = c.post(
            "/api/v1/_probe/validate", content=payload, headers={"content-type": "application/json"}
        )
        assert r.status_code == 422, payload
        assert r.json()["error"]["code"] == ErrorCode.VALIDATION_ERROR
        assert "leak-me" not in r.text


# --- SC-4 -----------------------------------------------------------------------------------------


def test_context_keys_change_with_every_context_dimension() -> None:
    p, rev, ent = uid(), uid(), uid()

    def model(**kw: Any) -> EvidenceContext:
        data: dict[str, Any] = {
            "kind": "model",
            "project_id": p,
            "revision_id": rev,
            "selected_entity_type": "wellbore",
            "selected_entity_id": ent,
            "as_of": {"kind": "instant", "instant": "2026-10-28T12:00:00Z"},
        }
        return EvidenceContext.model_validate(data | kw)

    base = model()
    keys = {
        context_cache_key(base),
        context_cache_key(model(project_id=uid())),
        context_cache_key(model(revision_id=uid())),
        context_cache_key(model(selected_entity_id=uid())),
        context_cache_key(model(selected_entity_type="component")),
        context_cache_key(model(as_of={"kind": "instant", "instant": "2026-10-28T12:00:01Z"})),
        context_cache_key(model(as_of={"kind": "day", "day": "2026-10-28", "timezone": "UTC"})),
        context_cache_key(
            model(as_of={"kind": "day", "day": "2026-10-28", "timezone": "Europe/Oslo"})
        ),
        context_cache_key(model(selected_entity_type=None, selected_entity_id=None, as_of=None)),
        context_cache_key(base, query={"family": "log"}),
        context_cache_key(base, algorithm_version="v2"),
        context_cache_key(
            EvidenceContext.model_validate(
                {"kind": "source", "project_id": p, "source_revision_id": rev}
            )
        ),
        context_cache_key(
            EvidenceContext.model_validate(
                {"kind": "draft", "project_id": p, "run_id": uid(), "revision_id": rev}
            )
        ),
    }
    assert len(keys) == 13
    assert context_cache_key(base) == context_cache_key(model())  # deterministic
    same_instant = model(as_of={"kind": "instant", "instant": "2026-10-28T08:00:00-04:00"})
    assert context_cache_key(same_instant) == context_cache_key(base)  # offsets normalize to UTC


def test_source_context_has_no_defaults_and_engineering_rejects_it() -> None:
    src = SourceContext(project_id=uid(), source_revision_id=uid())
    assert set(src.model_dump()) == {"kind", "project_id", "source_revision_id"}
    with pytest.raises(ContractError) as err:
        require_context_kind(src, frozenset({"model"}))
    assert err.value.code is ErrorCode.CONTEXT_KIND_NOT_ALLOWED
    require_context_kind(src, frozenset({"source", "model"}))  # source browsing needs no model
    draft = DraftContext(project_id=uid(), run_id=uid(), revision_id=uid())
    with pytest.raises(ContractError):
        require_context_kind(draft, frozenset({"model"}))


def test_query_context_entity_fields_are_explicit_pair() -> None:
    QueryContext(project_id=uid(), revision_id=uid())  # explicit nulls
    with pytest.raises(ValidationError):
        QueryContext(project_id=uid(), revision_id=uid(), selected_entity_id=uid())
    with pytest.raises(ValidationError):
        QueryContext(project_id=uid(), revision_id=uid(), selected_entity_type="well")


def test_as_of_day_requires_zone_and_instant_normalizes_to_utc() -> None:
    with pytest.raises(ValidationError):
        DayAsOf.model_validate({"day": "2026-10-28"})
    got = InstantAsOf(instant=datetime(2026, 10, 28, 8, tzinfo=timezone(timedelta(hours=-4))))
    assert got.instant == datetime(2026, 10, 28, 12, tzinfo=UTC)
    assert got.instant.utcoffset() == timedelta(0)


# --- SC-5 -----------------------------------------------------------------------------------------


def claim(
    key: str,
    cls: EvidenceClass,
    state: ValidationState = ValidationState.UNREVIEWED,
    records: bool = True,
) -> Claim:
    return Claim(
        claim_id=uid(),
        project_id=uid(),
        revision_id=uid(),
        subject_id=uid(),
        subject_type="component",
        attribute_key=key,
        value=ClaimValue.model_validate(
            {"kind": "quantity", "quantity": {"value": 1.0, "unit": "in"}}
        ),
        source_record_ids=[uid()] if records else [],
        validation_state=state,
        evidence_class=cls,
    )


@pytest.mark.parametrize("cls", [EvidenceClass.GENERIC, EvidenceClass.CATALOG_DERIVED])
@pytest.mark.parametrize("key", ["installed.outside_diameter", "installed.install_date"])
def test_generic_and_catalog_values_are_not_authoritative_installed_measurements(
    cls: EvidenceClass, key: str
) -> None:
    with pytest.raises(ValidationError, match="authoritative installed"):
        claim(key, cls)
    claim(
        key.replace("installed.", "generic." if cls is EvidenceClass.GENERIC else "catalog."), cls
    )


def test_installed_source_claim_needs_source_records() -> None:
    claim("installed.outside_diameter", EvidenceClass.SOURCE_RECORD)
    with pytest.raises(ValidationError):
        claim("installed.outside_diameter", EvidenceClass.SOURCE_RECORD, records=False)


def test_evidence_class_is_independent_of_validation_state() -> None:
    for cls in EvidenceClass:
        for state in ValidationState:
            key = {
                EvidenceClass.GENERIC: "generic.outside_diameter",
                EvidenceClass.CATALOG_DERIVED: "catalog.x",
            }.get(cls, "component.x")
            built = claim(key, cls, state)
            assert (built.evidence_class, built.validation_state) == (cls, state)
    assert claim("installed.depth", EvidenceClass.SOURCE_RECORD).validation_state is (
        ValidationState.UNREVIEWED
    )  # source evidence alone never implies valid


# --- SC-6 -----------------------------------------------------------------------------------------


def test_read_bounds_fail_rather_than_clamp() -> None:
    assert PageParams().limit == 50
    assert PageParams(limit=200).limit == 200
    for bad in (0, 201, -1):
        with pytest.raises(ValidationError):
            PageParams(limit=bad)
    assert NumericWindowParams(start=0, end=1, limit=5000).limit == 5000
    for bad_window in (
        {"start": 0, "end": 1, "limit": 5001},
        {"start": 1, "end": 1},
        {"start": 2, "end": 1},
    ):
        with pytest.raises(ValidationError):
            NumericWindowParams.model_validate(bad_window)


def test_http_bounds_are_422_not_silently_widened() -> None:
    app = FastAPI()
    from fastapi import Query

    @app.get("/page")
    def page(q: PageParams = Query()) -> dict[str, int]:  # noqa: B008
        return {"limit": q.limit}

    c = TestClient(app)
    assert c.get("/page", params={"limit": 200}).json() == {"limit": 200}
    assert c.get("/page", params={"limit": 201}).status_code == 422
    assert c.get("/page", params={"limit": 10, "bogus": 1}).status_code == 422
    _ = Depends
