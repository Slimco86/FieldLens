"""IN-11: text intake is tolerant by content (encoding, no extension) but binaries stay refused."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.engine import URL

from fieldlens.textenc import detect_encoding
from tests.upload_support import LAS, TEXT, make_api

LAS_TEXT = LAS.decode()
LATIN = "Inclination 45.5 \u00b0 azimuth 270 \u00b0 depth m\nstation 1  1000.0\n"


def test_text_intake_encodings() -> None:
    assert detect_encoding(TEXT) == "utf-8"
    assert detect_encoding("\ufeffabc\n".encode()) == "utf-8-sig"
    assert detect_encoding("MD INC AZI\n1 2 3\n".encode("utf-16")) == "utf-16"
    assert detect_encoding("MD INC AZI\n1 2 3\n".encode("utf-16-le")) == "utf-16-le"
    assert detect_encoding("MD INC AZI\n1 2 3\n".encode("utf-16-be")) == "utf-16-be"
    assert detect_encoding(LATIN.encode("cp1252")) == "cp1252"
    assert detect_encoding(LATIN.encode("latin-1")) == "cp1252"
    # binaries
    assert detect_encoding(bytes(range(256)) * 4) is None
    assert detect_encoding(b"abc\x00\x01\x02def" * 50) is None
    assert detect_encoding(b"\x7fELF\x02\x01\x01\x00" * 20) is None
    assert detect_encoding(b"\x01\x02\x03\x04\xe9\xe8" * 100) is None  # 8-bit, control-heavy
    assert detect_encoding(b"\x00\x00\x00\x00") is None


@pytest.mark.parametrize(
    ("name", "data", "encoding"),
    [
        ("Volve F_F-12_ACTUAL", LATIN.encode("cp1252"), "cp1252"),
        ("survey", "MD INC\n1 2\n".encode("utf-16-le"), "utf-16-le"),
        ("survey_be", "MD INC\n1 2\n".encode("utf-16-be"), "utf-16-be"),
        ("utf8_plain", b"ascii only\n", "utf-8"),
    ],
)
def test_extensionless_text_is_accepted_with_recorded_encoding(
    migrated_url: URL, tmp_path: Path, name: str, data: bytes, encoding: str
) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    r = api.upload(pid, [(name, data)])
    assert r.status_code == 202, r.text
    while api.worker.run_once():
        pass
    doc = api.documents(pid)[0]
    assert doc["format_family"] == "text"
    assert doc["origin_metadata"]["text_encoding"] == encoding
    while api.worker.extraction.run_once():
        pass
    rep = api.client.get(f"/api/v1/projects/{pid}/documents/{doc['document_id']}/extraction").json()
    assert rep["status"] == "unsupported"  # visible unsupported_profile, not a refusal
    assert {i["code"] for i in rep["issues"]} == {"UNSUPPORTED_FORMAT"}


def test_las_utf16_without_bom_is_detected_by_content(migrated_url: URL, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    r = api.upload(pid, [("noext", LAS_TEXT.encode("utf-16-le"))])
    assert r.status_code == 202, r.text
    while api.worker.run_once():
        pass
    doc = api.documents(pid)[0]
    assert doc["format_family"] == "las"
    assert doc["origin_metadata"]["text_encoding"] == "utf-16-le"
    while api.worker.extraction.run_once():
        pass
    rep = api.client.get(f"/api/v1/projects/{pid}/documents/{doc['document_id']}/extraction").json()
    assert rep["status"] != "unsupported"  # the LAS profile read the UTF-16 text by content


def test_binaries_and_executables_are_still_refused(migrated_url: URL, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    cases = {
        "nul.dat": (b"abc\x00\x01\x02def" * 50, "unsupported_signature"),
        "elf": (b"\x7fELF\x02\x01\x01" + b"\x00" * 64, "executable_content"),
        "ctrl": (b"\x01\x02\x03\x04\xe9\xe8" * 100, "unsupported_signature"),
        "script": (b"#!/bin/sh\necho hi\n", "executable_content"),
    }
    r = api.upload(pid, [(n, d) for n, (d, _) in cases.items()])
    assert r.status_code == 415
    refused = {f["filename"]: f["reason"] for f in r.json()["error"]["details"]["refused_files"]}
    assert refused == {n: reason for n, (_, reason) in cases.items()}
    assert api.blob_files() == []
