# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import get_settings

database_url = get_settings().database_url
engine = create_async_engine(
    database_url,
    future=True,
    connect_args={"timeout": 30} if database_url.startswith("sqlite") else {},
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


if database_url.startswith("sqlite"):

    @event.listens_for(engine.sync_engine, "connect")
    def configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
        """Allow concurrent async readers/writers to share the SQLite file."""
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=30000")
        finally:
            cursor.close()


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
