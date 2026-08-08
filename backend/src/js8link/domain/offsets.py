# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ReceivedMessage
from .modes import bandwidth_from_mode

NORMAL_OFFSET_LOW = 1000
NORMAL_OFFSET_HIGH = 2500


@dataclass(frozen=True)
class OffsetRecommendation:
    offset: int | None
    heartbeat_count: int
    message_count: int
    average_snr: float | None


async def available_offsets(session: AsyncSession, band: str | None) -> list[int]:
    """Return observed offsets for a band, newest first, plus the common JS8 offset."""
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    query = select(ReceivedMessage.offset).where(
        ReceivedMessage.offset.is_not(None),
        ReceivedMessage.received_at >= cutoff,
    )
    if band:
        query = query.where(ReceivedMessage.band == band)
    values = (await session.scalars(query)).all()
    return sorted({int(value) for value in values if value is not None} | {1500})


async def best_offset(
    session: AsyncSession,
    *,
    band: str | None,
    window_minutes: int = 15,
    current_offset: int | None = None,
    speed: int | None = None,
) -> OffsetRecommendation:
    """Choose a stable offset that does not overlap another received signal."""
    cutoff = datetime.now(UTC) - timedelta(minutes=window_minutes)
    query = select(ReceivedMessage).where(
        ReceivedMessage.offset.is_not(None),
        ReceivedMessage.received_at >= cutoff,
        ReceivedMessage.is_heartbeat.is_(False),
        ReceivedMessage.offset >= NORMAL_OFFSET_LOW,
        ReceivedMessage.offset <= NORMAL_OFFSET_HIGH,
    )
    if band:
        query = query.where(ReceivedMessage.band == band)
    messages = (await session.scalars(query)).all()
    if not messages:
        return OffsetRecommendation(None, 0, 0, None)

    grouped: dict[int, list[ReceivedMessage]] = defaultdict(list)
    for message in messages:
        if message.offset is not None:
            grouped[int(message.offset)].append(message)
    if not grouped:
        return OffsetRecommendation(None, 0, len(messages), None)

    mode_map = {0: "Normal", 1: "Fast", 2: "Turbo", 4: "Slow", 8: "JS8 60"}
    desired_mode = mode_map[speed] if speed is not None else None
    desired_bandwidth = bandwidth_from_mode(desired_mode)

    def overlaps(left_offset: int, left_bandwidth: int, right_offset: int, right_bandwidth: int) -> bool:
        return abs(left_offset - right_offset) < (left_bandwidth + right_bandwidth) / 2

    def conflicts_with_other(candidate: int) -> bool:
        return any(
            other_offset != candidate
            and overlaps(candidate, desired_bandwidth, other_offset, max(bandwidth_from_mode(row.mode) for row in rows))
            for other_offset, rows in grouped.items()
        )

    if current_offset is not None and current_offset in range(NORMAL_OFFSET_LOW, NORMAL_OFFSET_HIGH + 1):
        if not conflicts_with_other(current_offset):
            return OffsetRecommendation(current_offset, 0, len(messages), None)

    safe_groups = {
        offset: rows for offset, rows in grouped.items() if not conflicts_with_other(offset)
    }
    if not safe_groups:
        return OffsetRecommendation(current_offset, 0, len(messages), None)

    def score(item: tuple[int, list[ReceivedMessage]]) -> tuple[int, float, datetime]:
        _, rows = item
        snrs = [row.snr for row in rows if row.snr is not None]
        average_snr = sum(snrs) / len(snrs) if snrs else -999.0
        latest = max((row.received_at for row in rows), default=datetime.min.replace(tzinfo=UTC))
        return len(rows), average_snr, latest

    selected_offset, selected_rows = max(safe_groups.items(), key=score)
    snrs = [row.snr for row in selected_rows if row.snr is not None]
    return OffsetRecommendation(
        selected_offset,
        0,
        len(messages),
        sum(snrs) / len(snrs) if snrs else None,
    )
