"""Pytest fixtures for unit and integration testing."""

import pytest
from pathlib import Path
from daily_expenses_importer.core.db import Database


@pytest.fixture
def temp_db(tmp_path: Path) -> Database:
    db_file = tmp_path / "test.db"
    return Database(db_file)
