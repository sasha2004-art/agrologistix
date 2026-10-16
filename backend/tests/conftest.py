from collections.abc import Iterator
from pathlib import Path

import pytest
from app.core.config import Settings
from app.core.database import create_database_engine, init_database
from app.main import create_app
from fastapi.testclient import TestClient
from sqlmodel import Session

USER_PIN = "123456"
ADMIN_PIN = "654321"


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    settings = Settings(sqlite_db_path=str(tmp_path / "test.db"))
    engine = create_database_engine(settings)
    init_database(engine)
    with Session(engine) as database_session:
        yield database_session
    engine.dispose()


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(
        user_access_pin=USER_PIN,
        admin_access_pin=ADMIN_PIN,
        sqlite_db_path=str(tmp_path / "api.db"),
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client
