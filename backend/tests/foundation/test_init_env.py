"""FL-018 AC-5: idempotent, non-destructive bootstrap that never prints values."""

from __future__ import annotations

import importlib.util
import stat
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[3]
SENTINEL = "provider-key-must-not-appear-7c1e"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("init_env", REPO / "scripts/init_env.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


init_env = load_script()
EXAMPLE_KEYS = {
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "FIELDLENS_DB_PORT",
    "FIELDLENS_DATABASE_URL",
    "FIELDLENS_STORAGE_ROOT",
    "FIELDLENS_PROCESSING_PROVIDER",
    "FIELDLENS_PROCESSING_RUN_CAP_USD",
    "FIELDLENS_PROCESSING_META_INPUT_USD_PER_MTOK",
    "FIELDLENS_PROCESSING_META_OUTPUT_USD_PER_MTOK",
    "FIELDLENS_PROCESSING_MODEL_PAGES",
    "FIELDLENS_PW_CONNECT_WS_ENDPOINT",
    "FIELDLENS_PW_EXPOSE_NETWORK",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "TELEGRAM_INBOX",
    "TAIGA_USERNAME",
    "TAIGA_PASSWORD",
    "TAIGA_PROJECT_SLUG",
    "TAIGA_URL",
    "TAIGA_ALLOW_PUBLIC",
}


def project(tmp_path: Path) -> Path:
    (tmp_path / ".env.example").write_text((REPO / ".env.example").read_text(), encoding="utf-8")
    return tmp_path


def keys(path: Path) -> list[str]:
    return [
        line.split("=", 1)[0]
        for line in path.read_text().splitlines()
        if "=" in line and not line.startswith("#")
    ]


def test_example_declares_every_key_without_secrets() -> None:
    example = (REPO / ".env.example").read_text()
    assert {k for k, _, _ in init_env._example_blocks(example)} == EXAMPLE_KEYS
    assert "MODEL_API_KEY=" not in example


def test_creates_owner_only_env_with_generated_urlsafe_password(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = project(tmp_path)
    assert init_env.main(root) == 0
    env = root / ".env"
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    assert set(keys(env)) == EXAMPLE_KEYS
    password = next(
        line.split("=", 1)[1]
        for line in env.read_text().splitlines()
        if line.startswith("POSTGRES_PASSWORD=")
    )
    assert len(password) >= 40 and password != "generated-by-init-env"
    assert all(c.isalnum() or c in "-_" for c in password)
    out = capsys.readouterr()
    assert password not in out.out + out.err
    assert "POSTGRES_PASSWORD" in out.out  # names only


def test_second_run_changes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path)
    init_env.main(root)
    before = (root / ".env").read_bytes()
    capsys.readouterr()
    assert init_env.main(root) == 0
    assert (root / ".env").read_bytes() == before
    assert "nothing changed" in capsys.readouterr().out


@pytest.mark.parametrize("trailing_newline", [True, False])
def test_existing_lines_are_preserved_byte_for_byte_and_never_printed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], trailing_newline: bool
) -> None:
    root = project(tmp_path)
    original = f"MODEL_API_KEY={SENTINEL}\nPOSTGRES_USER=custom\n# note"
    original += "\n" if trailing_newline else ""
    env = root / ".env"
    env.write_bytes(original.encode())
    env.chmod(0o644)
    assert init_env.main(root) == 0
    data = env.read_bytes()
    assert data.startswith(original.encode())
    assert data.count(b"POSTGRES_USER=") == 1  # existing value kept, key not re-added
    assert b"POSTGRES_USER=custom" in data
    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    out = capsys.readouterr()
    assert SENTINEL not in out.out + out.err
    assert "custom" not in out.out + out.err
    assert "MODEL_API_KEY" not in out.out + out.err


def test_existing_password_is_never_overwritten(tmp_path: Path) -> None:
    root = project(tmp_path)
    env = root / ".env"
    env.write_text("POSTGRES_PASSWORD=keep-me\n")
    init_env.main(root)
    assert env.read_text().startswith("POSTGRES_PASSWORD=keep-me\n")
    assert env.read_text().count("POSTGRES_PASSWORD=") == 1


def test_missing_example_fails_without_creating_env(tmp_path: Path) -> None:
    assert init_env.main(tmp_path) == 1
    assert not (tmp_path / ".env").exists()


def test_generated_env_loads_through_the_shared_loader(tmp_path: Path) -> None:
    from fieldlens.localenv import load_local_env

    root = project(tmp_path)
    init_env.main(root)
    values = load_local_env(root / ".env")
    # localenv keeps its narrow allow-list: tooling keys (TELEGRAM_/TAIGA_) are not loaded here.
    assert set(values) == {k for k in EXAMPLE_KEYS if not k.startswith(("TELEGRAM_", "TAIGA_"))}
    url = values["FIELDLENS_DATABASE_URL"]
    assert values["POSTGRES_PASSWORD"] in url and "${" not in url
    assert url.endswith("@127.0.0.1:55432/fieldlens_app")
    assert values["FIELDLENS_PW_EXPOSE_NETWORK"] == "<loopback>"
