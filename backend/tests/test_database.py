from pathlib import Path

import pytest
from app.core.config import Settings
from app.core.database import apply_schema_migrations, create_database_engine
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError


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


def _columns(engine: Engine, table: str) -> set[str]:
    with engine.connect() as connection:
        return {row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({table})")}


def test_migration_adds_shipped_and_unmet_columns(tmp_path: Path) -> None:
    settings = Settings(sqlite_db_path=str(tmp_path / "legacy.db"))
    engine = create_database_engine(settings)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE simulation_run ("
            "id INTEGER PRIMARY KEY, created_at DATETIME, weather_mode VARCHAR, "
            "temp_c FLOAT, precip_mm FLOAT, total_tco_rub FLOAT, "
            "total_trip_cost_rub FLOAT, total_spoilage_loss_rub FLOAT, "
            "total_unmet_penalty_rub FLOAT, expected_net_profit_rub FLOAT, "
            "avg_freshness_pct FLOAT)"
        )

    apply_schema_migrations(engine)
    migrated = _columns(engine, "simulation_run")
    apply_schema_migrations(engine)

    engine.dispose()
    assert {"total_shipped_kg", "total_unmet_kg"} <= migrated


def test_migration_adds_delivered_kg_to_client_order(tmp_path: Path) -> None:
    settings = Settings(sqlite_db_path=str(tmp_path / "legacy-order.db"))
    engine = create_database_engine(settings)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE client_order ("
            "id INTEGER PRIMARY KEY, client_id INTEGER, product_id INTEGER, "
            "requested_kg FLOAT, purchase_price_rub FLOAT, unmet_penalty_rub FLOAT, "
            "delivery_status VARCHAR)"
        )
        connection.exec_driver_sql(
            "INSERT INTO client_order VALUES (1, 1, 1, 1000.0, 100.0, 5.0, 'pending')"
        )

    apply_schema_migrations(engine)
    migrated = _columns(engine, "client_order")
    apply_schema_migrations(engine)

    with engine.connect() as connection:
        delivered_kg = connection.exec_driver_sql(
            "SELECT delivered_kg FROM client_order WHERE id = 1"
        ).scalar_one()

    engine.dispose()
    assert "delivered_kg" in migrated
    assert delivered_kg == 0.0


def test_migration_adds_route_provider_and_refresh_metadata(tmp_path: Path) -> None:
    settings = Settings(sqlite_db_path=str(tmp_path / "legacy-routes.db"))
    engine = create_database_engine(settings)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE route_cache ("
            "pair_key VARCHAR(128) PRIMARY KEY, distance_km FLOAT, "
            "base_duration_min FLOAT, geojson_geometry TEXT)"
        )
        connection.exec_driver_sql("INSERT INTO route_cache VALUES ('pair', 10.0, 12.0, '[]')")

    apply_schema_migrations(engine)
    migrated = _columns(engine, "route_cache")
    apply_schema_migrations(engine)

    with engine.connect() as connection:
        source, checked_at = connection.exec_driver_sql(
            "SELECT source, mapbox_checked_at FROM route_cache WHERE pair_key = 'pair'"
        ).one()

    engine.dispose()
    assert {"source", "mapbox_checked_at"} <= migrated
    assert source == "fallback"
    assert checked_at is None


def test_migration_ignores_missing_tables(tmp_path: Path) -> None:
    settings = Settings(sqlite_db_path=str(tmp_path / "empty.db"))
    engine = create_database_engine(settings)

    apply_schema_migrations(engine)

    engine.dispose()
    assert _columns(engine, "simulation_run") == set()


def test_migration_allows_in_progress_delivery_status(tmp_path: Path) -> None:
    """Старый CHECK ('pending', 'delivered') пересобирается до трёх этапов."""

    settings = Settings(sqlite_db_path=str(tmp_path / "legacy-status.db"))
    engine = create_database_engine(settings)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE client_order ("
            "id INTEGER PRIMARY KEY, client_id INTEGER, product_id INTEGER, "
            "requested_kg FLOAT, purchase_price_rub FLOAT, unmet_penalty_rub FLOAT, "
            "delivered_kg FLOAT DEFAULT 0, delivery_status VARCHAR(16), "
            "CONSTRAINT ck_order_delivery_status "
            "CHECK (delivery_status IN ('pending', 'delivered')))"
        )
        connection.exec_driver_sql(
            "CREATE INDEX ix_client_order_client_id ON client_order (client_id)"
        )
        connection.exec_driver_sql(
            "INSERT INTO client_order VALUES (1, 7, 2, 1000.0, 100.0, 5.0, 0.0, 'pending')"
        )

    apply_schema_migrations(engine)
    # Повторный запуск ничего не ломает: миграция идемпотентна.
    apply_schema_migrations(engine)

    with engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE client_order SET delivery_status = 'in_progress' WHERE id = 1"
        )
        status = connection.exec_driver_sql(
            "SELECT delivery_status FROM client_order WHERE id = 1"
        ).scalar_one()
        row = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'client_order'"
        ).scalar_one()
        index_names = {
            index_row[0]
            for index_row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'client_order'"
            )
        }
        with pytest.raises(IntegrityError):
            connection.exec_driver_sql(
                "UPDATE client_order SET delivery_status = 'flying' WHERE id = 1"
            )

    engine.dispose()
    assert status == "in_progress"
    assert "in_progress" in row
    assert "ix_client_order_client_id" in index_names
