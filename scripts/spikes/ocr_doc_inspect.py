"""Structure-only inspection of a legacy Word (.doc, OLE2) file (TASK-030 phase A, experiment).

Safe by construction: olefile reads compound-file streams; everything else is bounded
``struct`` parsing of the FIB, the piece table (text) and the Data stream (picture records).
Nothing is executed, no macro source is read, nothing is converted or sent anywhere. Reports
counts and short facts only; never dumps the document text.
"""

from __future__ import annotations

import re
import struct
import sys
import zlib
from collections import Counter
from pathlib import Path
from typing import Any

import olefile  # type: ignore[import-untyped,import-not-found,unused-ignore]

MAX_STREAM = 64 * 1024 * 1024
BLIP_TYPES = {
    0xF01A: "emf",
    0xF01B: "wmf",
    0xF01C: "pict",
    0xF01D: "jpeg",
    0xF02A: "jpeg",
    0xF01E: "png",
    0xF01F: "dib",
    0xF029: "tiff",
    0xF020: "tiff",
}


def read_stream(ole: Any, name: str) -> bytes:
    if not ole.exists(name) or ole.get_size(name) > MAX_STREAM:
        return b""
    return bytes(ole.openstream(name).read())


def fib_clx(word: bytes) -> tuple[int, int, bool]:
    if len(word) < 0x200 or struct.unpack_from("<H", word, 0)[0] != 0xA5EC:
        raise ValueError("not a Word binary FIB")
    flags = struct.unpack_from("<H", word, 0x0A)[0]
    which_table_1 = bool(flags & 0x0200)
    encrypted = bool(flags & 0x0100)
    fc_clx, lcb_clx = struct.unpack_from("<II", word, 154 + 33 * 8)
    return fc_clx, lcb_clx, which_table_1 and not encrypted or which_table_1


def extract_text(word: bytes, table: bytes, fc_clx: int, lcb_clx: int) -> str:
    clx = table[fc_clx : fc_clx + lcb_clx]
    i = 0
    while i < len(clx) and clx[i] == 0x01:  # skip Prc entries
        i += 3 + struct.unpack_from("<H", clx, i + 1)[0]
    if i >= len(clx) or clx[i] != 0x02:
        raise ValueError("no piece table")
    lcb = struct.unpack_from("<I", clx, i + 1)[0]
    plc = clx[i + 5 : i + 5 + lcb]
    n = (len(plc) - 4) // 12
    cps = struct.unpack_from(f"<{n + 1}I", plc, 0)
    parts: list[str] = []
    for k in range(n):
        fc_raw = struct.unpack_from("<I", plc, 4 * (n + 1) + 8 * k + 2)[0]
        count = cps[k + 1] - cps[k]
        if count < 0 or count > 10_000_000:
            raise ValueError("bad piece length")
        if fc_raw & 0x40000000:  # compressed (cp1252)
            fc = (fc_raw & 0x3FFFFFFF) // 2
            parts.append(word[fc : fc + count].decode("cp1252", errors="replace"))
        else:
            parts.append(word[fc_raw : fc_raw + count * 2].decode("utf-16-le", errors="replace"))
    return "".join(parts)


def scan_blips(
    data: bytes, start: int, end: int, out: list[dict[str, Any]], depth: int = 0
) -> None:
    """Walk OfficeArt records (bounded depth/length) and collect BLIP records."""
    pos = start
    while pos + 8 <= end and depth < 8:
        ver_inst, rtype, rlen = struct.unpack_from("<HHI", data, pos)
        body = pos + 8
        if rtype < 0xF000 or body + rlen > end:
            return
        if ver_inst & 0xF == 0xF:
            scan_blips(data, body, body + rlen, out, depth + 1)
        elif rtype == 0xF007 and rlen > 36:  # OfficeArtFBSE: header, name, optional embedded BLIP
            name_len = data[body + 33]
            scan_blips(data, body + 36 + name_len, body + rlen, out, depth + 1)
        elif rtype in BLIP_TYPES:
            try:
                out.append(blip_info(data, body, rlen, rtype, ver_inst >> 4))
            except (struct.error, IndexError):
                out.append({"type": BLIP_TYPES[rtype], "record_bytes": rlen, "malformed": True})
        pos = body + rlen


def blip_info(data: bytes, body: int, rlen: int, rtype: int, inst: int) -> dict[str, Any]:
    kind = BLIP_TYPES[rtype]
    info: dict[str, Any] = {"type": kind, "record_bytes": rlen}
    two_uid = inst in (0x46B, 0x6E3, 0x6E1, 0x7A9, 0x3D5, 0x217, 0x543)
    off = body + 16 + (16 if two_uid else 0)
    if kind in ("emf", "wmf", "pict"):
        # metafile header: cbSize, rcBounds(16), ptSize(8), cbSave, compression, filter
        if off + 34 <= body + rlen:
            (cb_size,) = struct.unpack_from("<I", data, off)
            bounds = struct.unpack_from("<4i", data, off + 4)
            comp = data[off + 32]
            info.update(uncompressed=cb_size, bounds=bounds, deflate=comp == 0)
            if comp == 0 and cb_size <= 64 * 1024 * 1024:
                try:  # bounded decompress to verify the header record (EMF signature)
                    d = zlib.decompressobj().decompress(data[off + 34 : body + rlen], 1 << 20)
                    info["emf_sig_ok"] = kind != "emf" or d[40:44] == b" EMF"
                except zlib.error:
                    info["emf_sig_ok"] = False
    else:
        off += 1  # tag byte
        blob = data[off : body + rlen]
        info["blob"] = (off, body + rlen)
        if kind == "png" and blob[:8] == b"\x89PNG\r\n\x1a\n":
            info["px"] = struct.unpack(">II", blob[16:24])
        elif kind == "jpeg" and blob[:2] == b"\xff\xd8":
            p = 2
            while p + 9 < len(blob):
                if blob[p] != 0xFF:
                    break
                m = blob[p + 1]
                ln = struct.unpack(">H", blob[p + 2 : p + 4])[0]
                if m in (0xC0, 0xC1, 0xC2):
                    info["px"] = struct.unpack(">HH", blob[p + 5 : p + 9])[::-1]
                    break
                p += 2 + ln
        elif kind == "dib" and len(blob) >= 12:
            info["px"] = struct.unpack("<ii", blob[4:12])
    return info


def walk_pictures(data: bytes) -> list[dict[str, Any]]:
    """Find PICFAndOfficeArtData records. The Data stream is not a chain (it also holds SPRM
    data), so scan for the PICF signature (cbHeader 0x44, mm MM_SHAPE/MM_SHAPEFILE) and bound-check."""
    pics: list[dict[str, Any]] = []
    pos = 0
    while pos + 68 <= len(data) and len(pics) < 5000:
        lcb, cb_header, mm = struct.unpack_from("<IHH", data, pos)
        if cb_header == 68 and mm in (0x64, 0x66) and 68 < lcb <= len(data) - pos:
            found: list[dict[str, Any]] = []
            scan_blips(data, pos + cb_header, pos + lcb, found)
            if found:
                pics.append({"offset": pos, "lcb": lcb, "blips": found})
                pos += lcb
                continue
        pos += 1
    return pics


def main(path: str, extract_dir: str | None = None) -> None:
    ole = olefile.OleFileIO(path)
    streams = ["/".join(e) for e in ole.listdir(streams=True, storages=False)]
    print("streams:", {s: ole.get_size(s) for s in streams})
    print(
        "has_vba_macro_storage:",
        any(s.startswith("Macros/") or s.startswith("_VBA") for s in streams),
    )
    meta = ole.get_metadata()
    print(
        "summary: pages", meta.num_pages, "words", meta.num_words, "app", meta.creating_application
    )
    word = read_stream(ole, "WordDocument")
    fc_clx, lcb_clx, tbl1 = fib_clx(word)
    flags = struct.unpack_from("<H", word, 0x0A)[0]
    print("fib flags: encrypted", bool(flags & 0x100), "table", "1Table" if tbl1 else "0Table")
    table = read_stream(ole, "1Table" if tbl1 else "0Table")
    text = extract_text(word, table, fc_clx, lcb_clx)
    kw = [
        "tubing",
        "packer",
        "casing",
        "liner",
        "perforat",
        "pump",
        "hanger",
        "schematic",
        "mandrel",
    ]
    low = text.lower()
    print(
        "text_chars:",
        len(text),
        "picture_anchors(0x01):",
        text.count("\x01"),
        "table_cell_marks(0x07):",
        text.count("\x07"),
        "keywords:",
        {k: low.count(k) for k in kw},
    )
    heads = [
        m.group(0)[:80] for m in re.finditer(r"(?m)^\d+(?:\.\d+)*\s+[A-Z][^\r\n]{2,60}", text)
    ][:25]
    print("numbered headings (first 25, trimmed):", heads)
    pics = walk_pictures(read_stream(ole, "Data"))
    kinds = Counter(b["type"] for p in pics for b in p["blips"])
    print("data_stream_pictures:", len(pics), "blip_types:", dict(kinds))
    if extract_dir:  # raw PNG/JPEG blips to a gitignored scratch directory (never committed)
        out = Path(extract_dir)
        out.mkdir(parents=True, exist_ok=True)
        raw = read_stream(ole, "Data")
        for n, p in enumerate(pics):
            for b in p["blips"]:
                if "blob" in b and b["type"] in ("png", "jpeg"):
                    a, z = b["blob"]
                    (out / f"pic{n:02d}.{'jpg' if b['type'] == 'jpeg' else 'png'}").write_bytes(
                        raw[a:z]
                    )
    for p in pics[:60]:
        print(
            " ",
            p["offset"],
            p["lcb"],
            [
                (b["type"], b.get("px"), b.get("bounds"), b.get("emf_sig_ok"), b["record_bytes"])
                for b in p["blips"]
            ],
        )


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
