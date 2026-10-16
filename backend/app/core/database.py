from collections.abc import Generator
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, event
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import Settings, get_settings


def _database_url(path: str) -> str:
    if path == ":memory:":
        return "sqlite://"
    return f"sqlite:///{Path(path).expanduser()}"


def create_database_engine(settings: Settings | None = None) -> Engine:
    resolved_settings = settings or get_settings()
    database_path = Path(resolved_settings.sqlite_db_path).expanduser()
    if resolved_settings.sqlite_db_path != ":memory:":
        database_path.parent.mkdir(parents=True, exist_ok=True)

    database_engine = create_engine(
        _database_url(resolved_settings.sqlite_db_path),
        connect_args={"check_same_thread": False},
        echo=False,
    )

    @event.listens_for(database_engine, "connect")
    def set_sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    return database_engine


engine = create_database_engine()


def init_database() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
