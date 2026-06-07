import pytest
import database.db as db_module
from database.db import init_db


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    """Изолированная тестовая БД во временной директории."""
    db_file = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_file)
    init_db()
    return db_file
