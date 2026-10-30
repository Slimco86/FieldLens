"""Synthetic fixtures for the native-profile tests.

Everything here is generated in memory from invented values (no Volve content is committed).
Layouts mimic the shapes of the approved source families; the values are not real data."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any
from uuid import UUID
from xml.sax.saxutils import escape

from fieldlens.profiles.types import ParseContext, ProfileOutput

CTX = ParseContext(
    document_id=UUID("00000000-0000-0000-0000-0000000000d1"),
    source_revision_id=UUID("00000000-0000-0000-0000-0000000000a1"),
    sha256="0" * 64,
    filename="x",
)

WITSML_NS = "http://www.witsml.org/schemas/1series"


def write(tmp: Path, name: str, data: bytes | str) -> Path:
    path = tmp / name
    path.write_bytes(data if isinstance(data, bytes) else data.encode())
    return path


def witsml(plural: str, singular: str, body: str, *, well: str = "15/9-F-99") -> str:
    """Wrap an object body in a WITSML 1.4.1.1 document (synthetic F-99 well)."""
    return (
        f'<?xml version="1.0" encoding="UTF-8"?><{plural} xmlns="{WITSML_NS}" version="1.4.1.1">'
        f'<{singular} uidWell="W1" uidWellbore="B1" uid="O1"><nameWell>{well}</nameWell>'
        f"<nameWellbore>{well}</nameWellbore><name>synthetic</name>{body}</{singular}></{plural}>"
    )


def station(uid: str, md: str, tvd: str, incl: str, azi: str, time: str | None = None) -> str:
    t = f"<dTimStn>{time}</dTimStn>" if time else ""
    return (
        f'<trajectoryStation uid="{uid}">{t}<typeTrajStation>MWD</typeTrajStation>'
        f'<md uom="m">{md}</md><tvd uom="m">{tvd}</tvd><incl uom="dega">{incl}</incl>'
        f'<azi uom="dega">{azi}</azi></trajectoryStation>'
    )


def _cell(ref: str, value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, tuple) and value[0] == "date":
        return f'<c r="{ref}" s="1"><v>{value[1]}</v></c>'
    if isinstance(value, int | float):
        return f'<c r="{ref}"><v>{value}</v></c>'
    return f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'


def _col(i: int) -> str:
    return "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[i]


def xlsx_bytes(sheets: dict[str, list[list[Any]]]) -> bytes:
    """Minimal workbook; ``("date", serial)`` cells use a date-formatted style."""
    names = list(sheets)
    sheet_tags = "".join(
        f'<sheet name="{escape(n)}" sheetId="{i + 1}" r:id="rId{i + 1}"/>'
        for i, n in enumerate(names)
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8"?><workbook '
        'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{sheet_tags}</sheets></workbook>"
    )
    rels = "".join(
        f'<Relationship Id="rId{i + 1}" Type="x" Target="worksheets/sheet{i + 1}.xml"/>'
        for i in range(len(names))
    )
    styles = (
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<cellXfs count="2"><xf numFmtId="0"/><xf numFmtId="14"/></cellXfs></styleSheet>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f"{rels}</Relationships>",
        )
        zf.writestr("xl/styles.xml", styles)
        for i, rows in enumerate(sheets.values()):
            body = "".join(
                f'<row r="{r + 1}">'
                + "".join(_cell(f"{_col(c)}{r + 1}", v) for c, v in enumerate(row))
                + "</row>"
                for r, row in enumerate(rows)
            )
            zf.writestr(
                f"xl/worksheets/sheet{i + 1}.xml",
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f"<sheetData>{body}</sheetData></worksheet>",
            )
    return buf.getvalue()


def codes(out: ProfileOutput) -> set[str]:
    return {f.code for f in out.findings}


def text_pdf(pages: list[list[str]]) -> bytes:
    """Hand-built text PDF (Courier, one string per line) so layout extraction keeps spacing."""
    objs: list[bytes] = []
    n_pages = len(pages)
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(n_pages))
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n_pages} >>".encode())
    font_id = 3 + 2 * n_pages
    for i, lines in enumerate(pages):
        ops = ["BT /F1 8 Tf 9 TL 20 780 Td"]
        for line in lines:
            safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            ops.append(f"({safe}) Tj T*")
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1")
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} 0 R "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>".encode()
        )
        objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)
