"""FL-018: root .env loading, precedence, key filtering and explicit DB-less configuration."""

from __future__ import annotations

from pathlib import Path

import pytest

from fieldlens import config
from fieldlens.config import Settings
from fieldlens.localenv import ENV_FILE, REPO_ROOT, load_local_env

SENTINEL = "provider-key-must-not-appear-7c1e"
URL = "postgresql+psycopg://svc:pw_-Ab12@127.0.0.1:55432/fieldlens_app"


def write_env(path: Path) -> Path:
    path.write_text(
        f"MODEL_API_KEY={SENTINEL}\n"
        "POSTGRES_USER=svc\n"
        "POSTGRES_PASSWORD=pw_-Ab12\n"
        "POSTGRES_DB=fieldlens_app\n"
        "FIELDLENS_DB_PORT=55432\n"
        "FIELDLENS_DATABASE_URL=postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}"
        "@127.0.0.1:${FIELDLENS_DB_PORT}/${POSTGRES_DB}\n"
        "FIELDLENS_STORAGE_ROOT=.local/store\n"
        "OTHER_SECRET=nope\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("FIELDLENS_DATABASE_URL", "FIELDLENS_STORAGE_ROOT", "FIELDLENS_PORT"):
        monkeypatch.delenv(key, raising=False)


def test_env_file_is_anchored_to_the_repository_root_not_the_cwd() -> None:
    assert ENV_FILE == REPO_ROOT / ".env"
    assert (REPO_ROOT / "compose.yaml").is_file()
    assert Settings.model_config["env_file"] == ENV_FILE


def test_loader_returns_only_fieldlens_and_postgres_keys_with_interpolation(
    tmp_path: Path,
) -> None:
    values = load_local_env(write_env(tmp_path / ".env"))
    assert set(values) == {
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "FIELDLENS_DB_PORT",
        "FIELDLENS_DATABASE_URL",
        "FIELDLENS_STORAGE_ROOT",
    }
    assert values["FIELDLENS_DATABASE_URL"] == URL
    assert SENTINEL not in repr(values)


def test_loader_missing_file_is_empty(tmp_path: Path) -> None:
    assert load_local_env(tmp_path / "absent.env") == {}


def test_settings_read_the_env_file_ignoring_unrelated_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = write_env(tmp_path / ".env")
    settings = Settings(_env_file=env)
    assert settings.database_url is not None
    assert settings.database_url.get_secret_value() == URL
    assert settings.storage_root == REPO_ROOT / ".local/store"
    assert SENTINEL not in repr(settings) and SENTINEL not in str(settings.redacted())
    assert not hasattr(settings, "model_api_key")


def test_real_environment_overrides_the_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = write_env(tmp_path / ".env")
    other = "postgresql+psycopg://env:pw@127.0.0.1:2/other_db"
    monkeypatch.setenv("FIELDLENS_DATABASE_URL", other)
    settings = Settings(_env_file=env)
    assert settings.database_url is not None
    assert settings.database_url.get_secret_value() == other


def test_explicit_no_env_file_configuration_ignores_dotenv(tmp_path: Path) -> None:
    write_env(tmp_path / ".env")
    assert Settings(_env_file=None).database_url is None
    assert Settings(_env_file=None, database_url=None).database_url is None


def test_default_settings_follow_the_configured_root_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)  # cwd independence: the path is absolute

    class Rooted(Settings):
        model_config = {**Settings.model_config, "env_file": write_env(tmp_path / "x.env")}

    assert Rooted().database_url is not None


def test_absolute_storage_root_is_kept(tmp_path: Path) -> None:
    assert Settings(_env_file=None, storage_root=tmp_path).storage_root == tmp_path


def test_provider_key_is_never_adopted_from_process_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODEL_API_KEY", SENTINEL)
    assert SENTINEL not in repr(Settings(_env_file=None))
    assert "model_api_key" not in config.Settings.model_fields
