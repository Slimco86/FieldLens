"""toolenv: dotenv-like parsing, prefix filter, env override, worktree fallback."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parents[3]


def load_script(name: str) -> ModuleType:
    scripts = str(REPO / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


toolenv = load_script("toolenv")


def test_value_semantics_and_prefix_filter(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "# comment\n\n"
        "TELEGRAM_BOT_TOKEN=abc#def # trailing comment\n"
        "export TELEGRAM_CHAT_ID='-100 # kept'  # gone\n"
        'TAIGA_PASSWORD="pa ss#word"\n'
        "TAIGA_URL=\n"
        "POSTGRES_PASSWORD=must-not-load\n"
        "MODEL_API_KEY=must-not-load\n",
        encoding="utf-8",
    )
    values = toolenv.load(tmp_path, {})
    assert values == {
        "TELEGRAM_BOT_TOKEN": "abc#def",
        "TELEGRAM_CHAT_ID": "-100 # kept",
        "TAIGA_PASSWORD": "pa ss#word",
        "TAIGA_URL": "",
    }
    assert set(toolenv.secret_values(values)) == {"abc#def", "-100 # kept", "pa ss#word"}


def test_environment_overrides_file(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("TELEGRAM_CHAT_ID=1\nTAIGA_URL=file\n", encoding="utf-8")
    env = {"TELEGRAM_CHAT_ID": "2", "TAIGA_USERNAME": "u", "HOME": "/x"}
    assert toolenv.load(tmp_path, env) == {
        "TELEGRAM_CHAT_ID": "2",
        "TAIGA_URL": "file",
        "TAIGA_USERNAME": "u",
    }


def test_linked_worktree_falls_back_to_main_checkout(tmp_path: Path) -> None:
    main = tmp_path / "main"
    main.mkdir()

    def git(*args: str) -> None:
        subprocess.run(  # noqa: S603
            ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],  # noqa: S607
            cwd=main,
            check=True,
            capture_output=True,
        )

    git("init", "-q")
    git("commit", "-q", "--allow-empty", "-m", "init")
    (main / ".env").write_text("TELEGRAM_CHAT_ID=77\n", encoding="utf-8")
    linked = tmp_path / "linked"
    git("worktree", "add", "-q", "-b", "wt", str(linked))
    assert toolenv.env_file_path(linked).resolve() == (main / ".env").resolve()
    assert toolenv.load(linked, {}) == {"TELEGRAM_CHAT_ID": "77"}
    (linked / ".env").write_text("TELEGRAM_CHAT_ID=88\n", encoding="utf-8")
    assert toolenv.load(linked, {}) == {"TELEGRAM_CHAT_ID": "88"}
