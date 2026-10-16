from collections.abc import Iterator
from pathlib import Path

import pytest
from app.core.config import Settings
from app.core.database import create_database_engine, init_database
from sqlmodel import Session


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    settings = Settings(sqlite_db_path=str(tmp_path / "test.db"))
    engine = create_database_engine(settings)
    init_database(engine)
    with Session(engine) as database_session:
        yield database_session
    engine.dispose()
