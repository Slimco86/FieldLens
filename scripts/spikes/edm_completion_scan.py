"""TASK-044 spike: per-wellbore completion/production-equipment scan over an EDM row dump.

Input is the JSONL written by ``edm_census.py dump`` (tables CD_WELL, CD_WELLBORE, CD_ASSEMBLY,
CD_ASSEMBLY_COMP, CD_WEQP_PACKER, CD_CASE, CD_SCENARIO). Wells are keyed by ``well_id`` and
wellbores by ``wellbore_id`` (never by display name: several wellbores in other wells carry the
name of another well). Prints counts and locators (file line numbers) only; no unit or datum is
assumed: values are reported as the file states them.

    python scripts/spikes/edm_completion_scan.py DUMP.jsonl [WELL_COMMON_NAME ...]"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PROD_STRING_TYPES = {"Tubing", "Liner", "Tieback"}
PROD_SECT = {"TBG", "PKR", "PBR", "HOO", "SRP", "SS", "SL", "LH", "TUJ"}  # TBG/PKR/... sect codes


def load(path: Path) -> dict[str, list[dict[str, Any]]]:
    by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for line in path.read_text().splitlines():
        row = json.loads(line)
        by[row["_t"]].append(row)
    return by


def scan(by: dict[str, list[dict[str, Any]]], names: list[str]) -> dict[str, Any]:
    wells = {w["well_id"]: w for w in by["CD_WELL"] if w["well_common_name"] in names}
    out: dict[str, Any] = {}
    for wb in by["CD_WELLBORE"]:
        if wb["well_id"] not in wells:
            continue
        wid = wb["wellbore_id"]
        asm = [a for a in by["CD_ASSEMBLY"] if a["wellbore_id"] == wid]
        comps = [c for c in by["CD_ASSEMBLY_COMP"] if c["wellbore_id"] == wid]
        out[f"{wells[wb['well_id']]['well_common_name']} / {wb['wellbore_name']} ({wid})"] = {
            "line": wb["_line"],
            "assemblies_by_type_phase": dict(
                Counter(f"{a.get('string_type')}|{a.get('phase')}" for a in asm)
            ),
            "production_assemblies": [
                (a["_line"], a["assembly_id"], a.get("assembly_name"), a.get("string_type"))
                for a in asm
                if a.get("string_type") in PROD_STRING_TYPES
            ],
            "production_class_assemblies": sum(a.get("string_class") == "Production" for a in asm),
            "completion_components": [
                (c["_line"], c["assembly_id"], c.get("sect_type_code"), c.get("od_body"))
                for c in comps
                if c.get("sect_type_code") in PROD_SECT
            ],
            "packers": [
                (p["_line"], p["assembly_id"], p.get("packer_depth"))
                for p in by["CD_WEQP_PACKER"]
                if p["wellbore_id"] == wid
            ],
            "cases_by_phase": dict(
                Counter(str(c.get("phase")) for c in by["CD_CASE"] if c["wellbore_id"] == wid)
            ),
        }
    return out


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    names = argv[2:] or ["F-12", "F-14", "F-5"]
    print(json.dumps(scan(load(Path(argv[1])), names), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
