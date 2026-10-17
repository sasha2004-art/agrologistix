from collections.abc import Generator
from pathlib import Path
from typing import Any

from fastapi import Request
from sqlalchemy import Engine, event
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import Settings, get_settings
from app.models import erp_models, run_models  # noqa: F401  (register SQLModel tables)


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


# Columns added after the first release; create_all() never alters existing tables.
_SQLITE_MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    (
        "simulation_run",
        "total_shipped_kg",
        "ALTER TABLE simulation_run ADD COLUMN total_shipped_kg FLOAT NOT NULL DEFAULT 0",
    ),
    (
        "simulation_run",
        "total_unmet_kg",
        "ALTER TABLE simulation_run ADD COLUMN total_unmet_kg FLOAT NOT NULL DEFAULT 0",
    ),
    (
        "client_order",
        "delivered_kg",
        "ALTER TABLE client_order ADD COLUMN delivered_kg FLOAT NOT NULL DEFAULT 0",
    ),
    (
        "route_cache",
        "source",
        "ALTER TABLE route_cache ADD COLUMN source VARCHAR(16) NOT NULL DEFAULT 'fallback'",
    ),
    (
        "route_cache",
        "mapbox_checked_at",
        "ALTER TABLE route_cache ADD COLUMN mapbox_checked_at FLOAT",
    ),
    (
        "truck",
        "has_insulation",
        "ALTER TABLE truck ADD COLUMN has_insulation BOOLEAN NOT NULL DEFAULT 0",
    ),
)


def apply_schema_migrations(database_engine: Engine) -> None:
    """Add missing columns to existing SQLite tables (idempotent)."""

    with database_engine.begin() as connection:
        for table, column, statement in _SQLITE_MIGRATIONS:
            existing = {row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({table})")}
            if not existing:
                continue
            if column not in existing:
                connection.exec_driver_sql(statement)


def init_database(database_engine: Engine) -> None:
    SQLModel.metadata.create_all(database_engine)
    apply_schema_migrations(database_engine)


def get_session(request: Request) -> Generator[Session, None, None]:
    database_engine: Engine = request.app.state.db_engine
    with Session(database_engine) as session:
        yield session
