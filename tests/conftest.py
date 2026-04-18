from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from twrminal.config import Settings, StorageCfg


@pytest.fixture
def tmp_settings(tmp_path: Path) -> Iterator[Settings]:
    cfg = Settings(
        storage=StorageCfg(db_path=tmp_path / "db.sqlite"),
    )
    cfg.config_file = tmp_path / "config.toml"
    yield cfg
