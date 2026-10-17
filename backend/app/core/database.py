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

    _migrate_delivery_status_constraint(database_engine)


def _migrate_delivery_status_constraint(database_engine: Engine) -> None:
    """Расширяет CHECK у ``client_order.delivery_status`` до трёх этапов поставки.

    SQLite не умеет менять CHECK у существующей таблицы, поэтому базу приходится
    пересобирать: создать копию с новым ограничением, перенести строки, удалить
    старую и переименовать. Шаг идемпотентен: если в сохранённом DDL уже есть
    ``in_progress``, ничего не делаем. Индексы после DROP TABLE создаются заново.
    """

    old_check = "delivery_status IN ('pending', 'delivered')"
    new_statuses = "('pending', 'in_progress', 'delivered')"
    new_check = f"delivery_status IN {new_statuses}"

    # PRAGMA foreign_keys не работает внутри транзакции: пересборка идёт в AUTOCOMMIT.
    with database_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        row = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'client_order'"
        ).first()
        if row is None or not row[0]:
            return
        ddl: str = row[0]
        if new_statuses in ddl or old_check not in ddl:
            return

        indexes = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'index' AND tbl_name = 'client_order' AND sql IS NOT NULL"
        ).all()
        rebuilt = ddl.replace(old_check, new_check)
        rebuilt = rebuilt.replace(
            "CREATE TABLE client_order", "CREATE TABLE client_order_rebuilt", 1
        )

        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.exec_driver_sql("BEGIN")
        connection.exec_driver_sql(rebuilt)
        connection.exec_driver_sql("INSERT INTO client_order_rebuilt SELECT * FROM client_order")
        connection.exec_driver_sql("DROP TABLE client_order")
        connection.exec_driver_sql("ALTER TABLE client_order_rebuilt RENAME TO client_order")
        for (index_sql,) in indexes:
            connection.exec_driver_sql(index_sql)
        connection.exec_driver_sql("COMMIT")
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")


def init_database(database_engine: Engine) -> None:
    SQLModel.metadata.create_all(database_engine)
    apply_schema_migrations(database_engine)


def get_session(request: Request) -> Generator[Session, None, None]:
    database_engine: Engine = request.app.state.db_engine
    with Session(database_engine) as session:
        yield session
