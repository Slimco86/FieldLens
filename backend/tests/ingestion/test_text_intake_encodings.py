"""IN-11: text intake is tolerant by content (encoding, no extension) but binaries stay refused."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.engine import URL

from fieldlens.textenc import detect_encoding, open_text, refine_encoding, sniff_path
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


def test_late_non_utf8_byte_is_cp1252(tmp_path: Path) -> None:
    path = tmp_path / "late.dat"
    path.write_bytes(b"MD 1000.0\n" * 12000 + b"deg \xb0\n")
    assert sniff_path(path) == "cp1252"
    with open_text(path) as fh:
        assert fh.read().endswith("deg \u00b0\n")
    ok = tmp_path / "ok.dat"  # valid multibyte characters straddling chunk edges stay utf-8
    ok.write_bytes(b"a" * (1024 * 1024 - 1) + "\u00b0\u6df1".encode() * 5)
    assert refine_encoding(ok, "utf-8") == "utf-8"
    cut = tmp_path / "cut.dat"  # truncated multibyte sequence at EOF is not valid utf-8
    cut.write_bytes(b"abc " * 100 + "\u6df1".encode()[:2])
    assert refine_encoding(cut, "utf-8") == "cp1252"
    binary = tmp_path / "bin.dat"
    binary.write_bytes(b"a" * 70000 + b"\x01\x02\xe9" * 5000)
    assert sniff_path(binary) is None


def test_late_nuls_and_controls_are_refused(tmp_path: Path) -> None:
    clean = b"MD 1000.0\n" * 7000  # > 64 KiB of clean text before the tail
    late_utf8 = tmp_path / "late_nul_utf8.dat"
    late_utf8.write_bytes(clean + b"\x00" * 50000)
    assert sniff_path(late_utf8) is None
    late_cp = tmp_path / "late_nul_cp.dat"
    late_cp.write_bytes(clean + b"deg \xb0\n" + b"\x00" * 50000)
    assert sniff_path(late_cp) is None
    one_nul = tmp_path / "one_nul.dat"
    one_nul.write_bytes(clean + b"\x00" + clean)
    assert sniff_path(one_nul) is None
    ctrl = tmp_path / "late_ctrl.dat"
    ctrl.write_bytes(clean + b"\x01\x02" * 20000)
    assert sniff_path(ctrl) is None
    stray = tmp_path / "stray.dat"  # a few stray controls stay accepted
    stray.write_bytes(clean + b"\x01\x02\x1a" + clean)
    assert sniff_path(stray) == "utf-8"


def test_utf16_with_nuls_is_still_accepted(tmp_path: Path) -> None:
    bom = tmp_path / "bom16.dat"
    bom.write_bytes(b"\xff\xfe" + ("MD 1000.0\n" * 9000).encode("utf-16-le"))
    assert sniff_path(bom) == "utf-16"
    bomless = tmp_path / "nobom16.dat"
    bomless.write_bytes(("MD 1000.0\n" * 9000).encode("utf-16-le"))
    assert sniff_path(bomless) == "utf-16-le"


def test_bomless_utf16_cjk_is_refused() -> None:
    for codec in ("utf-16-le", "utf-16-be"):
        assert detect_encoding("\u6df1\u5ea6\u6d4b\u91cf".encode(codec) * 20) is None
    assert (
        detect_encoding(
            ("MD 1000.0 m, inclinaison 45.5 \u00b0, r\u00e9sum\u00e9 du puits\n" * 20).encode(
                "cp1252"
            )
        )
        == "cp1252"
    )


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
