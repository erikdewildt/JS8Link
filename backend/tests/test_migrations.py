# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command


def test_initial_migration_creates_schema(tmp_path: Path) -> None:
    database = tmp_path / "test.sqlite"
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database}")
    command.upgrade(config, "head")
    tables = set(inspect(create_engine(f"sqlite:///{database}")).get_table_names())
    assert {
        "app_config",
        "auth_config",
        "received_messages",
        "transmitted_messages",
        "activity_events",
        "js8_api_messages",
        "stations",
        "station_links",
        "station_queries",
        "arq_receipts",
        "diagnostic_traces",
        "diagnostic_processing",
    }.issubset(tables)
    transmitted_columns = {
        column["name"]
        for column in inspect(create_engine(f"sqlite:///{database}")).get_columns("transmitted_messages")
    }
    assert {
        "delivery_mode",
        "protocol_id",
        "protocol_version",
        "delivery_status",
        "ack_deadline",
        "delivered_at",
    }.issubset(transmitted_columns)
