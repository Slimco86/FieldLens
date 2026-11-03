"""Visual-only isolation (AG-5): no calculation/engineering/retrieval module imports the asset spec."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parents[2] / "fieldlens"
ALLOWED = {
    ROOT / "app.py",  # router registration
    ROOT / "persistence" / "models.py",  # table metadata
    ROOT / "contracts" / "registry.py",  # DTO registry
    # S5 orchestration (TASK-079): composes the designer; calculation modules still never import it
    ROOT / "reconstruction" / "design_stage.py",
    ROOT / "reconstruction" / "live.py",
    ROOT / "reconstruction" / "runtime.py",
    ROOT / "reconstruction" / "stages.py",
}
PATTERN = re.compile(
    r"(fieldlens\.assetspec|fieldlens\.contracts\.asset_spec|\bimport asset_spec\b|\basset_spec,)"
)


def test_nothing_outside_assetspec_imports_the_spec() -> None:
    offenders = []
    for path in ROOT.rglob("*.py"):
        if "assetspec" in path.parts or path == ROOT / "contracts" / "asset_spec.py":
            continue
        if path in ALLOWED:
            continue
        if PATTERN.search(path.read_text()):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_engineering_modules_exist_and_are_checked() -> None:
    # guards the walk above: the calculation package is among the scanned files
    assert any((ROOT / "engineering").rglob("*.py"))
