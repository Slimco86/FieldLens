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


def test_only_model_api_key_is_adopted_by_settings_and_only_as_a_secret(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Owner decision 2026-10-30 13:41 EDT: the one provider key is MODEL_API_KEY.
    monkeypatch.setenv("MODEL_API_KEY", SENTINEL)
    settings = Settings(_env_file=None)
    assert settings.meta_api_key is not None
    assert settings.meta_api_key.get_secret_value() == SENTINEL
    assert SENTINEL not in repr(settings) and SENTINEL not in str(settings.redacted())
    assert SENTINEL not in repr(config.Settings.model_fields)
    monkeypatch.delenv("MODEL_API_KEY")
    env_file = tmp_path / "k.env"
    env_file.write_text(f"MODEL_API_KEY={SENTINEL}\nOTHER_SECRET=nope\n", encoding="utf-8")
    from_file = Settings(_env_file=env_file)
    assert from_file.meta_api_key is not None
    assert "nope" not in repr(from_file) and SENTINEL not in repr(from_file)
    assert "other_secret" not in config.Settings.model_fields
    # the scripts/tests loader still never returns it
    assert "MODEL_API_KEY" not in load_local_env(env_file)


def test_default_tests_never_see_a_real_provider_key() -> None:
    assert Settings().meta_api_key is None  # blank process variable beats the root .env
    assert Settings(_env_file=None).meta_api_key is None


def test_unexpanded_references_from_an_injected_environment_are_resolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Editors/terminals can export .env lines verbatim, leaving ${VAR} in the value.
    monkeypatch.setenv(
        "FIELDLENS_DATABASE_URL",
        "postgresql+psycopg://${POSTGRES_USER}:pw@127.0.0.1:${FIELDLENS_DB_PORT}/${POSTGRES_DB}",
    )
    monkeypatch.setenv("POSTGRES_USER", "svc")
    monkeypatch.setenv("FIELDLENS_DB_PORT", "55432")
    monkeypatch.setattr(config, "load_local_env", lambda: {"POSTGRES_DB": "fieldlens_app"})
    url = Settings(_env_file=None).database_url
    assert url is not None
    assert url.get_secret_value() == "postgresql+psycopg://svc:pw@127.0.0.1:55432/fieldlens_app"


def test_undefined_reference_is_rejected_without_echoing_the_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FIELDLENS_DATABASE_URL", "postgresql+psycopg://u:secretpw@h/${NOPE_DB}")
    monkeypatch.setattr(config, "load_local_env", lambda: {})
    with pytest.raises(ValueError, match="NOPE_DB") as raised:
        Settings(_env_file=None)
    assert "secretpw" not in str(raised.value)
