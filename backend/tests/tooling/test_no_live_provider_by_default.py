"""Default tests and the e2e runner can never reach the live Meta provider, whatever .env says."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from fieldlens.config import Settings

ROOT = Path(__file__).resolve().parents[3]


def _run_e2e(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(ROOT / "backend"))
    spec = importlib.util.spec_from_file_location(
        "run_e2e_hermetic_probe", ROOT / "scripts/run_e2e.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_e2e_hermetic_probe"] = module
    spec.loader.exec_module(module)
    return module


def test_e2e_runner_pins_the_stub_whatever_the_ambient_environment_says(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _run_e2e(monkeypatch)
    ambient = {
        "FIELDLENS_PROCESSING_PROVIDER": "meta",
        "MODEL_API_KEY": "not-a-real-key-for-tests",
        "FIELDLENS_LIVE_META": "1",
        "PATH": "/usr/bin",
    }
    env = module.hermetic_env(ambient)
    assert env["FIELDLENS_PROCESSING_PROVIDER"] == "stub"
    assert env["MODEL_API_KEY"] == "" and env["FIELDLENS_LIVE_META"] == ""
    assert env["PATH"] == "/usr/bin"  # everything else passes through


def test_e2e_api_process_receives_the_stub_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _run_e2e(monkeypatch)
    seen: dict[str, Any] = {}

    def fake_popen(cmd: list[str], **kwargs: Any) -> object:
        seen.update(kwargs)
        return object()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    module._start_api(
        {
            "FIELDLENS_PROCESSING_PROVIDER": "meta",
            "MODEL_API_KEY": "not-a-real-key-for-tests",
            "FIELDLENS_LIVE_META": "1",
        }
    )
    env = seen["env"]
    assert env["FIELDLENS_PROCESSING_PROVIDER"] == "stub"
    assert env["MODEL_API_KEY"] == "" and env["FIELDLENS_LIVE_META"] == ""


def test_default_tests_never_build_a_meta_runtime_from_the_repo_env() -> None:
    settings = Settings()  # reads the repo .env exactly like the real app would
    assert settings.processing_provider == "stub"
    assert not settings.meta_api_key


def test_a_dotenv_asking_for_meta_is_overridden_in_default_tests(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "FIELDLENS_PROCESSING_PROVIDER=meta\nMODEL_API_KEY=not-a-real-key-for-tests\n",
        encoding="utf-8",
    )
    settings = Settings(_env_file=dotenv)  # type: ignore[call-arg]
    assert settings.processing_provider == "stub" and not settings.meta_api_key
