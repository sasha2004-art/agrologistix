from pathlib import Path

from app.core.config import Settings
from app.core.database import create_database_engine


def test_sqlite_file_uses_wal_and_foreign_keys(tmp_path: Path) -> None:
    database_path = tmp_path / "nested" / "test.db"
    settings = Settings(sqlite_db_path=str(database_path))
    engine = create_database_engine(settings)

    with engine.connect() as connection:
        journal_mode = connection.exec_driver_sql("PRAGMA journal_mode").scalar_one()
        foreign_keys = connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one()

    engine.dispose()
    assert database_path.exists()
    assert journal_mode.lower() == "wal"
    assert foreign_keys == 1
