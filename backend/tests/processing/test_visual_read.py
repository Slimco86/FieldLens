"""TASK-115 (MODEL_VISUAL_READ VR-1..VR-8): scanned pages as images, non-PDF documents as sections.

Scripted provider that records the parts it was sent; nothing reaches a network or spends credit.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from sqlalchemy.engine import URL

from fieldlens.assistant.messages import ImagePart, TextPart
from fieldlens.assistant.stub import text_response
from fieldlens.candidates.pages import PageError
from fieldlens.processing import document_text as dt
from fieldlens.processing import identity_read as ir
from tests.processing.test_document_identity import (
    PAGE_QUOTE,
    USAGE,
    Model,
    answer,
    build_model,
    ident,
)


def scanned_pdf(pages: int) -> bytes:
    buf = io.BytesIO()
    imgs = [Image.new("RGB", (200 + i, 260), (255 - i, 255, 255)) for i in range(pages)]
    imgs[0].save(buf, "PDF", save_all=True, append_images=imgs[1:])
    return buf.getvalue()


def xlsx(sheet_xml: str, *, extra: dict[str, str] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types xmlns='x'/>")
        z.writestr(
            "xl/workbook.xml",
            "<workbook xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main' "
            "xmlns:r='http://schemas.openxmlformats.org/officeDocument/2006/relationships'>"
            "<sheets><sheet name='S1' sheetId='1' r:id='rId1'/></sheets></workbook>",
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            "<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>"
            "<Relationship Id='rId1' Target='worksheets/sheet1.xml' Type='t'/></Relationships>",
        )
        z.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        for name, body in (extra or {}).items():
            z.writestr(name, body)
    return buf.getvalue()


SHEET = (
    "<worksheet xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'><sheetData>"
    "<row r='1'><c r='A1' t='inlineStr'><is><t>Wellbore 15/9-F-12 B</t></is></c></row>"
    "</sheetData></worksheet>"
)
HOSTILE = "<!DOCTYPE x [<!ENTITY a 'b'>]>" + SHEET


class Store:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def open(self, key: str) -> Any:  # pragma: no cover - unused by the helpers below
        raise NotImplementedError


def images(m: Model, call: int) -> list[ImagePart]:
    return [
        p for msg in m.provider.calls[call].messages for p in msg.parts if isinstance(p, ImagePart)
    ]


def texts(m: Model, call: int) -> list[str]:
    return [
        p.text
        for msg in m.provider.calls[call].messages
        for p in msg.parts
        if isinstance(p, TextPart)
    ]


def test_vr1_scanned_pdf_is_sent_as_images_in_order_chunked_by_images_per_call(
    migrated_url: URL, tmp_path: Path
) -> None:
    script = [answer(identities=[]), answer(identities=[])]
    m = build_model(
        migrated_url,
        tmp_path,
        script,
        files={"scan.pdf": scanned_pdf(6)},
        visual=True,
        images_per_call=4,
        model_pages=10,
    )
    est = m.world.estimate("scan.pdf").json()
    assert est["estimate"]["image_pages"] == [1, 2, 3, 4, 5, 6]
    assert est["estimate"]["estimated_usd"] != "0" and est["estimate"]["unit"] == "page"
    assert m.world.confirm(est).status_code == 202 and m.world.drain() == 1
    run = m.world.get(est["run_id"])
    assert run["status"] == "succeeded"
    assert [len(images(m, i)) for i in range(len(m.provider.calls))] == [4, 2]
    headers = [t for t in texts(m, 0) if t.startswith("PAGE ")]
    assert headers == [f"PAGE {n} (image):" for n in (1, 2, 3, 4)]
    assert m.read("scan.pdf")["read_mode"] == "image"
    assert Decimal_le(run["actual_usd"], run["estimate"]["estimated_usd"])  # PE-1


def Decimal_le(a: str, b: str) -> bool:
    from decimal import Decimal

    return Decimal(a) <= Decimal(b)


def test_vr3_render_failure_marks_pages_unreadable_and_all_unreadable_spends_nothing(
    migrated_url: URL, tmp_path: Path
) -> None:
    m = build_model(
        migrated_url,
        tmp_path,
        [answer()],
        files={"scan.pdf": scanned_pdf(2)},
        visual=True,
    )

    class Broken:
        def render(self, *a: Any, **k: Any) -> Any:
            raise PageError("render_failed", "boom")

    step: Any = m.world.rt.step
    step._renderer = Broken()
    run = m.run("scan.pdf")
    assert m.provider.calls == []
    assert run["actual_usd"] in ("0", "0.000000")
    read = m.read("scan.pdf")
    assert "no_text_layer" in [w["code"] for w in read["warnings"]]


def test_vr4_prompt_v2_states_untrusted_and_exact_transcription() -> None:
    assert ir.PROMPT_VERSION == "doc-identity-2"
    system = ir.SYSTEM_PROMPT.lower()
    assert "untrusted" in system and "exactly" in system and "image" in system
    parts = ir.build_messages({1: "text page"})[0].parts
    assert len(parts) == 1 and isinstance(parts[0], TextPart)  # text body unchanged


def test_vr5_image_identity_kept_when_name_in_quote_stored_as_image_proposal(
    migrated_url: URL, tmp_path: Path
) -> None:
    good = ident(quote=PAGE_QUOTE, page=1)
    bad = ident(name="99/9-Z-9", quote=PAGE_QUOTE, page=1)
    off = ident(quote=PAGE_QUOTE, page=9)  # not a page of the call
    m = build_model(
        migrated_url,
        tmp_path,
        [
            text_response(
                json.dumps({"category": None, "tags": [], "identities": [good, bad, off]}), USAGE
            )
        ],
        files={"scan.pdf": scanned_pdf(2)},
        visual=True,
    )
    m.run("scan.pdf")
    read = m.read("scan.pdf")
    (identity,) = read["identities"]
    assert identity["read_mode"] == "image" and identity["status"] == "model_proposal"
    assert identity["resolution"] == "unresolved"
    assert "image_pages_unverified" in [w["code"] for w in read["warnings"]]


def test_vr5_image_identity_never_links_even_with_a_matching_wellbore(
    migrated_url: URL, tmp_path: Path
) -> None:
    from fieldlens.assetspec.sweep import wellbore_documents
    from fieldlens.persistence.session import session_scope
    from tests.processing.test_document_identity import seed_wellbore

    m = build_model(
        migrated_url,
        tmp_path,
        [answer(identities=[ident()])],
        files={"scan.pdf": scanned_pdf(1)},
        visual=True,
    )
    wb = seed_wellbore(m, "15/9-F-12 B")
    m.run("scan.pdf")
    assert m.read("scan.pdf")["identities"][0]["resolution"] == "unresolved"
    from uuid import UUID

    with session_scope(m.world.api.client.app.state.session_factory) as s:
        assert wellbore_documents(s, UUID(m.world.project_id), wb) == []


@pytest.mark.parametrize("name", ["well.ascii", "well", "well.dat", "well.asc"])
def test_vr6_non_pdf_documents_are_read_as_sections_whatever_the_filename(
    migrated_url: URL, tmp_path: Path, name: str
) -> None:
    body = (
        "Wellbore 15/9-F-12 B completion summary\n" + "free text line about the job\n" * 5
    ).encode()
    m = build_model(migrated_url, tmp_path, [answer()], files={name: body})
    state = m.world.states()[name]
    assert state["processable"] is True and state["unit"] == "section"
    run = m.run(name)
    assert run["status"] == "succeeded" and run["estimate"]["unit"] == "section"
    assert "<<<DOCUMENT_PAGE 1>>>" in "\n".join(texts(m, 0))
    assert m.read(name)["read_mode"] == "text"


def test_vr6_binary_preview_is_one_bounded_labelled_section() -> None:
    blob = bytes(range(256)) * 200 + b"printable run here " * 800
    out = dt.binary_preview(blob)
    assert out.startswith("[BINARY PREVIEW") and len(out) < 32_000


def test_vr6_split_sections_respects_limit_and_lines() -> None:
    text = "\n".join(f"line {i:05d} " + "x" * 50 for i in range(1000))
    parts = dt.split_sections(text)
    assert len(parts) > 1 and all(len(p) <= 12_000 for p in parts)
    assert "\n".join(parts).replace("\n\n", "\n").count("line ") == 1000


def _store_with(tmp_path: Path, data: bytes) -> tuple[Any, str]:
    class S:
        def path(self, key: str) -> Path:
            return tmp_path / key

    (tmp_path / "k").write_bytes(data)
    return S(), "k"


def test_vr6_xlsx_hostile_doctype_refused_and_clean_workbook_read() -> None:
    assert "Wellbore 15/9-F-12 B" in dt.xlsx_text(xlsx(SHEET))
    for hostile in (xlsx(HOSTILE), xlsx(SHEET, extra={"xl/sharedStrings.xml": HOSTILE})):
        with pytest.raises(dt.DocumentTextError) as err:
            dt.xlsx_text(hostile)
        assert err.value.code == "unsafe_workbook"


def test_vr8_legacy_empty_read_is_not_a_cache_hit(migrated_url: URL, tmp_path: Path) -> None:
    m = build_model(migrated_url, tmp_path, [answer()], files={"n.txt": b"Wellbore 15/9-F-12 B\n"})
    m.run("n.txt")
    assert len(m.provider.calls) == 1
    m.world.sql(
        "UPDATE document_model_result SET input_tokens = 0, output_tokens = 0, "
        'warnings = CAST(\'[{"code": "no_text_layer"}]\' AS jsonb)'
    )
    m.provider.script.append(answer()) if hasattr(m.provider, "script") else None
    second = m.run("n.txt")
    assert second["documents"][0]["cache_hit"] is False
