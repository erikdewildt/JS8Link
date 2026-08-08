# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
"""Tests for the offset recommendation engine."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from js8link.domain.offsets import available_offsets, best_offset
from js8link.models import Base, ReceivedMessage


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _insert_message(
    session: AsyncSession,
    offset: int,
    band: str = "20m",
    snr: int = -10,
    received_at: datetime | None = None,
    is_heartbeat: bool = False,
    mode: str = "Normal",
) -> ReceivedMessage:
    msg = ReceivedMessage(
        callsign="PA3ABC",
        text="TEST",
        offset=offset,
        band=band,
        snr=snr,
        received_at=received_at or _now(),
        is_heartbeat=is_heartbeat,
        mode=mode,
    )
    session.add(msg)
    await session.flush()
    return msg


@pytest.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite://", future=True, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session


class TestAvailableOffsets:
    async def test_no_messages_returns_default(self, db_session: AsyncSession) -> None:
        offsets = await available_offsets(db_session, None)
        assert offsets == [1500]

    async def test_with_messages_includes_observed_and_default(self, db_session: AsyncSession) -> None:
        await _insert_message(db_session, 1700)
        await _insert_message(db_session, 2100)
        await db_session.commit()

        offsets = await available_offsets(db_session, None)
        assert 1500 in offsets
        assert 1700 in offsets
        assert 2100 in offsets

    async def test_band_filter(self, db_session: AsyncSession) -> None:
        await _insert_message(db_session, 1700, band="20m")
        await _insert_message(db_session, 1800, band="40m")
        await db_session.commit()

        offsets = await available_offsets(db_session, "20m")
        assert 1700 in offsets
        assert 1800 not in offsets

    async def test_duplicates_are_merged(self, db_session: AsyncSession) -> None:
        await _insert_message(db_session, 1700)
        await _insert_message(db_session, 1700)
        await db_session.commit()

        offsets = await available_offsets(db_session, None)
        assert offsets.count(1700) == 1


class TestBestOffset:
    async def test_no_messages_returns_none(self, db_session: AsyncSession) -> None:
        rec = await best_offset(db_session, band=None)
        assert rec.offset is None
        assert rec.message_count == 0

    async def test_with_messages_returns_busiest_offset(self, db_session: AsyncSession) -> None:
        # 1700 has 3 messages, 2000 has 1 — 1700 should win
        for _ in range(3):
            await _insert_message(db_session, 1700)
        await _insert_message(db_session, 2000)
        await db_session.commit()

        rec = await best_offset(db_session, band=None)
        assert rec.offset == 1700
        assert rec.message_count == 4

    async def test_prefers_current_offset_if_no_conflict(self, db_session: AsyncSession) -> None:
        # Only traffic at 2000, current at 1500 — no overlap in Normal mode (50 Hz)
        await _insert_message(db_session, 2000, snr=-5)
        await db_session.commit()

        rec = await best_offset(db_session, band=None, current_offset=1500)
        assert rec.offset == 1500  # Current offset preferred

    async def test_avoids_current_offset_if_conflict(self, db_session: AsyncSession) -> None:
        # Traffic at 1520, current at 1500 — overlap in Normal mode (50Hz bw, 20Hz apart < 25Hz)
        await _insert_message(db_session, 1520, snr=-5)
        await db_session.commit()

        rec = await best_offset(db_session, band=None, current_offset=1500)
        assert rec.offset != 1500

    async def test_band_filter(self, db_session: AsyncSession) -> None:
        await _insert_message(db_session, 1700, band="20m")
        await _insert_message(db_session, 1800, band="40m")
        await db_session.commit()

        rec = await best_offset(db_session, band="20m")
        assert rec.offset == 1700

    async def test_returns_none_when_all_conflict(self, db_session: AsyncSession) -> None:
        """When every offset conflicts and no current offset is provided, return none."""
        # In Turbo mode (160 Hz bw), offsets at 1500 and 1600 overlap (100 < 160)
        await _insert_message(db_session, 1500, mode="Turbo")
        await _insert_message(db_session, 1600, mode="Turbo")
        await db_session.commit()

        rec = await best_offset(db_session, band=None, speed=2)  # Turbo
        assert rec.offset is None

    async def test_average_snr_is_computed(self, db_session: AsyncSession) -> None:
        await _insert_message(db_session, 1700, snr=-5)
        await _insert_message(db_session, 1700, snr=-15)
        await db_session.commit()

        rec = await best_offset(db_session, band=None)
        assert rec.average_snr is not None
        assert rec.average_snr == pytest.approx(-10.0)

    async def test_respects_window_minutes(self, db_session: AsyncSession) -> None:
        old = _now() - timedelta(minutes=30)
        recent = _now() - timedelta(minutes=5)

        await _insert_message(db_session, 1700, received_at=old)
        await _insert_message(db_session, 2000, received_at=recent)
        await db_session.commit()

        rec = await best_offset(db_session, band=None, window_minutes=10)
        # Only the recent message should be considered
        assert rec.offset == 2000

    async def test_filters_heartbeats(self, db_session: AsyncSession) -> None:
        await _insert_message(db_session, 1700, is_heartbeat=True)
        await _insert_message(db_session, 2000, is_heartbeat=False)
        await db_session.commit()

        rec = await best_offset(db_session, band=None)
        assert rec.offset == 2000

    async def test_offsets_outside_normal_range_excluded(self, db_session: AsyncSession) -> None:
        await _insert_message(db_session, 500)  # Below NORMAL_OFFSET_LOW
        await _insert_message(db_session, 3000)  # Above NORMAL_OFFSET_HIGH
        await _insert_message(db_session, 1500)  # Valid
        await db_session.commit()

        rec = await best_offset(db_session, band=None)
        assert rec.offset == 1500
