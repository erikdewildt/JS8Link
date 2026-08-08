# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
"""Async test infrastructure for the JS8Link FastAPI backend.

Provides fixtures for:
- In-memory SQLite database with all tables
- httpx.AsyncClient with ASGITransport for async FastAPI testing
- Mocked JS8Call client (connected or disconnected)
- Dependency override for get_session
"""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ---------------------------------------------------------------------------
# Prevent the app from attempting real TCP connections to JS8Call.
# This patches the connect_client helper that is called both during
# on_startup and inside the setup endpoint.
# ---------------------------------------------------------------------------
_connect_client_patch = patch(
    "js8link.app.connect_client",
    AsyncMock(
        return_value={
            "type": "STATION.GET_CALLSIGN",
            "params": {"CALLSIGN": "K1ABC"},
            "value": "",
        }
    ),
)
_connect_client_patch.start()

from js8link.app import app  # noqa: E402
from js8link.db import get_session  # noqa: E402
from js8link.models import Base  # noqa: E402

# ---------------------------------------------------------------------------
# Prevent on_startup from running during the ASGI lifespan.
# This keeps ``client`` at ``None`` (no background tasks, no real connection
# attempt) so that our fixtures are in full control.
# ---------------------------------------------------------------------------
app.router.on_startup.clear()


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def async_engine():
    """An in-memory SQLite engine with all application tables created."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    # Avoid ``async with conn`` — its __aexit__ uses asyncio.create_task +
    # shield which suffers a GC race on CPython 3.14.
    conn = await engine.connect()
    try:
        await conn.run_sync(Base.metadata.create_all)
        await conn.commit()
    finally:
        await conn.close()

    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def async_session(async_engine) -> AsyncIterator[AsyncSession]:
    """An async session bound to the in-memory SQLite database."""
    session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        await session.close()


@pytest_asyncio.fixture
async def app_with_db(async_session):
    """The FastAPI app with get_session overridden to use the in-memory database."""
    async def override_get_session():
        yield async_session

    app.dependency_overrides[get_session] = override_get_session
    try:
        yield app
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# JS8Call client mock
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def mock_js8call() -> MagicMock:
    """A MagicMock that mimics a connected JS8CallClient.

    We do **not** use ``spec=JS8CallClient`` because the spec would
    reject instance attributes such as ``version``, ``connected`` and
    ``version_tuple`` (they are set inside ``__init__``, not declared
    at class level).
    """
    mock = MagicMock()
    mock.connected = True
    mock.version = "3.0.0"
    mock.close = AsyncMock()  # needed by config/setup endpoints that call await client.close()

    async def _request(message_type: str, value: str = "", params: dict | None = None):
        """Return a realistic JS8Call response for each request type."""
        if message_type == "RIG.GET_FREQ":
            return {"type": "RIG.FREQ", "params": {"DIAL": 14074000, "OFFSET": 1500}, "value": ""}
        if message_type == "MODE.GET_SPEED":
            return {"type": "MODE.SPEED", "params": {"SPEED": 0}, "value": ""}
        if message_type == "STATION.GET_GRID":
            return {"type": "STATION.GRID", "params": {}, "value": "FN42"}
        if message_type == "STATION.GET_INFO":
            return {"type": "STATION.INFO", "params": {}, "value": "JS8Link Test"}
        if message_type == "STATION.GET_STATUS":
            return {"type": "STATION.STATUS", "params": {}, "value": "Testing"}
        if message_type == "TX.GET_QUEUE_DEPTH":
            return {"type": "TX.QUEUE_DEPTH", "params": {"DEPTH": 0}, "value": ""}
        if message_type == "STATION.GET_OS":
            return {
                "type": "STATION.GET_OS",
                "params": {"OS_NAME": "TestOS", "OS_KERNEL": "linux", "OS_KERNEL_VERSION": "1.0"},
                "value": "",
            }
        if message_type == "RX.GET_BAND_ACTIVITY":
            return {"type": "RX.BAND_ACTIVITY", "params": {}, "value": ""}
        if message_type == "STATION.GET_CONFIG":
            return {
                "type": "STATION.CONFIG",
                "params": {
                    "AUTO_REPLY": False,
                    "JS8HB": False,
                    "HBACK": True,
                    "MULTI_DECODER": False,
                    "HB_INTERVAL": 15,
                    "MONITOR": True,
                    "TX_ENABLED": True,
                    "GROUPS": [],
                    "AVOID_ALLCALL": False,
                },
                "value": "",
            }
        if message_type == "STATION.GET_SPOT":
            return {"type": "STATION.SPOT", "params": {"value": False}, "value": ""}
        # Generic fallback for unknown request types
        return {"type": message_type, "params": {}, "value": ""}

    mock.request = AsyncMock(side_effect=_request)
    mock.send = AsyncMock(return_value=None)
    return mock


# ---------------------------------------------------------------------------
# HTTP client fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def async_client(app_with_db, mock_js8call) -> AsyncIterator[AsyncClient]:
    """An httpx.AsyncClient wired to the app with a *connected* JS8Call mock.

    The ``js8link.app.client`` global is patched with the mock so every
    endpoint sees ``client.connected == True``.
    """
    with patch("js8link.app.client", mock_js8call):
        transport = ASGITransport(app=app_with_db)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest_asyncio.fixture
async def async_client_disconnected(app_with_db) -> AsyncIterator[AsyncClient]:
    """An httpx.AsyncClient wired to the app *without* a connected JS8Call mock.

    The ``js8link.app.client`` global is ``None`` (on_startup was cleared),
    so endpoints that require a connection will return 503.
    """
    transport = ASGITransport(app=app_with_db)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
