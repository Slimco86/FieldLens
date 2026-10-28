"""Independent QA counterexamples, retained as foundation regressions."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from fieldlens.contracts.context import NumericWindowParams, PageParams
from fieldlens.contracts.evidence import Claim, EvidenceLink, Locator, Quantity
from fieldlens.contracts.identity import SourceDocument
from fieldlens.contracts.quality import QualityIssue


@pytest.mark.parametrize("field", ["document_id", "source_revision_id"])
@pytest.mark.parametrize("missing", [False, True])
def test_source_link_cannot_disagree_with_nested_locator(field: str, missing: bool) -> None:
    doc, rev = uuid4(), uuid4()
    data = {
        "document_id": doc,
        "source_revision_id": rev,
        "locator": {
            "kind": "pdf",
            "document_id": doc,
            "source_revision_id": rev,
            "page": 1,
        },
    }
    data[field] = None if missing else uuid4()
    with pytest.raises(ValidationError):
        EvidenceLink.model_validate(data)


def test_issue_cannot_hide_foreign_locator_revision_behind_null_link() -> None:
    with pytest.raises(ValidationError):
        QualityIssue.model_validate(
            {
                "issue_id": uuid4(),
                "context": {"kind": "source", "project_id": uuid4(), "source_revision_id": uuid4()},
                "code": "EXTRACTION_PARTIAL",
                "severity": "warning",
                "message": "Missing page",
                "producer_name": "test",
                "producer_version": "1",
                "producer_key": "test",
                "created_at": datetime.now(UTC),
                "evidence_links": [
                    {
                        "locator": {
                            "kind": "pdf",
                            "document_id": uuid4(),
                            "source_revision_id": uuid4(),
                            "page": 1,
                        },
                    }
                ],
            }
        )


@pytest.mark.parametrize(
    "evidence_class,key",
    [
        ("generic", "component.outer_diameter"),
        ("catalog_derived", "component.installation_date"),
        ("generic", "catalog.outer_diameter"),
        ("catalog_derived", "generic.installation_date"),
        ("source_record", "generic.outer_diameter"),
        ("derived", "catalog.installation_date"),
    ],
)
def test_claim_namespace_cannot_bypass_authority(evidence_class: str, key: str) -> None:
    with pytest.raises(ValidationError):
        Claim.model_validate(
            {
                "claim_id": uuid4(),
                "project_id": uuid4(),
                "revision_id": uuid4(),
                "subject_id": uuid4(),
                "subject_type": "component",
                "attribute_key": key,
                "value": {"kind": "text", "text": "illustrative"},
                "evidence_class": evidence_class,
                "source_record_ids": [uuid4()],
            }
        )


@pytest.mark.parametrize(
    "evidence_class,key",
    [
        ("generic", "generic.outer_diameter"),
        ("catalog_derived", "catalog.nominal_diameter"),
    ],
)
def test_non_authoritative_claim_can_be_valid(evidence_class: str, key: str) -> None:
    claim = Claim.model_validate(
        {
            "claim_id": uuid4(),
            "project_id": uuid4(),
            "revision_id": uuid4(),
            "subject_id": uuid4(),
            "subject_type": "component",
            "attribute_key": key,
            "value": {"kind": "text", "text": "illustrative"},
            "evidence_class": evidence_class,
            "validation_state": "valid",
        }
    )
    assert claim.validation_state == "valid"


@pytest.mark.parametrize("number", [float("nan"), float("inf"), float("-inf")])
def test_nested_origin_metadata_rejects_nonfinite_values(number: float) -> None:
    with pytest.raises(ValidationError):
        SourceDocument(
            document_id=uuid4(),
            project_id=uuid4(),
            sha256="a" * 64,
            size_bytes=1,
            original_filename="synthetic.txt",
            created_at=datetime.now(UTC),
            origin_metadata={"nested": [{"x": number}]},
        )


def test_origin_metadata_roundtrips_valid_json_without_coercion() -> None:
    doc = SourceDocument(
        document_id=uuid4(),
        project_id=uuid4(),
        sha256="a" * 64,
        size_bytes=1,
        original_filename="synthetic.txt",
        created_at=datetime.now(UTC),
        origin_metadata={"nested": [1, 2.5, True, None, {"source": "fixture"}]},
    )
    assert SourceDocument.model_validate_json(doc.model_dump_json()) == doc


@pytest.mark.parametrize("region", [[-5, -5, 99, 99], [0.5, 0.5, 0.1, 0.1], [0, 0, 0, 1]])
def test_embedded_image_region_must_be_normalized_and_ordered(region: list[float]) -> None:
    with pytest.raises(ValidationError):
        Locator.model_validate(
            {
                "kind": "embedded_image",
                "document_id": uuid4(),
                "source_revision_id": uuid4(),
                "container_item_index": 0,
                "image_sha256": "a" * 64,
                "region": region,
            }
        )


@pytest.mark.parametrize("blank", ["", " ", "\t\n"])
def test_quantity_requires_nonblank_units_and_reasons(blank: str) -> None:
    with pytest.raises(ValidationError):
        Quantity(value=1, unit=blank)
    with pytest.raises(ValidationError):
        Quantity(value=None, unknown_reason=blank)
    with pytest.raises(ValidationError):
        Quantity(
            value=1, unit="m", normalized_value=1, normalized_unit=blank, conversion_validated=True
        )


@pytest.mark.parametrize("limit", [True, False, 1.5, "1.0"])
def test_read_limits_are_strict_integers(limit: object) -> None:
    with pytest.raises(ValidationError):
        PageParams.model_validate({"limit": limit})
    with pytest.raises(ValidationError):
        NumericWindowParams.model_validate({"start": 0, "end": 1, "limit": limit})
