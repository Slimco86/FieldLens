"""The e2e runner's API port is overridable for lane-safe runs and defaults to 8101."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _load(monkeypatch: pytest.MonkeyPatch, value: str | None) -> ModuleType:
    if value is None:
        monkeypatch.delenv("FIELDLENS_E2E_API_PORT", raising=False)
    else:
        monkeypatch.setenv("FIELDLENS_E2E_API_PORT", value)
    monkeypatch.syspath_prepend(str(ROOT / "backend"))
    spec = importlib.util.spec_from_file_location("run_e2e_port_probe", ROOT / "scripts/run_e2e.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_e2e_port_probe"] = module
    spec.loader.exec_module(module)
    return module


def test_default_port_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _load(monkeypatch, None).API_PORT == 8101


def test_port_override_applies(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _load(monkeypatch, "8181").API_PORT == 8181


@pytest.mark.parametrize("bad", ["abc", "80", "70000"])
def test_invalid_port_is_refused(monkeypatch: pytest.MonkeyPatch, bad: str) -> None:
    with pytest.raises(RuntimeError, match="FIELDLENS_E2E_API_PORT"):
        _load(monkeypatch, bad)


def test_storage_root_is_fresh_per_run_unless_explicit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = _load(monkeypatch, None)
    with module.e2e_storage_root(None) as first:
        (first / "leftover.bin").write_bytes(b"x")
    assert not first.exists()
    with module.e2e_storage_root(None) as second:
        assert list(second.iterdir()) == [] and second != first
    with module.e2e_storage_root(str(tmp_path / "explicit")) as chosen:
        assert chosen == tmp_path / "explicit" / "e2e"
    assert chosen.is_dir()
