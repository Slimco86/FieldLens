from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.engine import URL

from tests.retrieval.support import World, make_world


@pytest.fixture
def world(migrated_url: URL, tmp_path: Path) -> World:
    return make_world(migrated_url, tmp_path, embedding_provider="none")
