# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
"""Integration tests for the JS8Link ARQ/1 protocol.

These tests exercise encoding/decoding, duplicate detection, acknowledgement
handling, the delivery state machine, and edge cases.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from js8link.domain.arq import ARQ_VERSION, ack_timeout_seconds, encode_ack, encode_data, new_message_id, parse_envelope
from js8link.models import ArqReceipt, Base, ReceivedMessage, TransmittedMessage

# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
async def db_session() -> AsyncSession:
    """In-memory SQLite session with all ARQ tables."""
    engine = create_async_engine("sqlite+aiosqlite://", future=True, echo=False)

    # Avoid ``engine.begin()`` and ``async with session`` context managers:
    # their __aexit__ methods use asyncio.create_task + shield which suffers
    # a GC race on CPython 3.14 where the task is collected before shield()
    # can await it (https://github.com/sqlalchemy/sqlalchemy/issues/12120).
    conn = await engine.connect()
    try:
        await conn.run_sync(Base.metadata.create_all)
        await conn.commit()
    finally:
        await conn.close()

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        await session.close()
        await engine.dispose()


@pytest.fixture
def fixed_message_id() -> str:
    return "7Q2M9C"


# ── Encoding / Decoding ──────────────────────────────────────────────────


class TestEncodeDecode:
    def test_data_round_trip_preserves_payload(self):
        encoded = encode_data("HELLO WORLD", "7Q2M9C")
        assert encoded == "HELLO WORLD ~1D7Q2M9C"

        env = parse_envelope(encoded)
        assert env is not None
        assert env.payload == "HELLO WORLD"
        assert env.version == 1
        assert env.opcode == "D"
        assert env.message_id == "7Q2M9C"

    def test_data_with_trailing_diamond(self):
        """JS8Call appends a diamond symbol after transmission."""
        env = parse_envelope("MSG ~1DABCDEF ♢")
        assert env is not None
        assert env.payload == "MSG"
        assert env.message_id == "ABCDEF"

    def test_data_with_only_diamond_no_space(self):
        env = parse_envelope("HI ~1D7Q2M9C♢")
        assert env is not None
        assert env.payload == "HI"

    def test_ack_round_trip(self):
        ack = encode_ack("7Q2M9C")
        assert ack == "~1A7Q2M9C"
        env = parse_envelope(ack)
        assert env is not None
        assert env.opcode == "A"
        assert env.payload == ""

    def test_ack_with_callsign_prefix(self):
        """ACK may have a callsign prefix for readability."""
        env = parse_envelope("PA3ABC ~1A7Q2M9C")
        assert env is not None
        assert env.opcode == "A"
        assert env.message_id == "7Q2M9C"
        assert env.payload == "PA3ABC"

    def test_ack_with_diamond(self):
        env = parse_envelope("~1A7Q2M9C ♢")
        assert env is not None
        assert env.opcode == "A"

    def test_invalid_suffix_too_short(self):
        """Message ID must be exactly six characters."""
        assert parse_envelope("HI ~1DABC") is None

    def test_invalid_suffix_wrong_chars(self):
        """Message ID uses Crockford Base32 — I, L, O, U are excluded."""
        assert parse_envelope("HI ~1DILLOUZ") is None

    def test_invalid_suffix_wrong_opcode(self):
        assert parse_envelope("HI ~1X7Q2M9C") is None

    def test_invalid_suffix_no_version(self):
        assert parse_envelope("HI ~D7Q2M9C") is None

    def test_embedded_tilde_not_matched(self):
        """A tilde mid-text without proper suffix format is ignored."""
        assert parse_envelope("CALL ~1 but not really") is None

    def test_trailing_tilde_prefix_but_no_suffix(self):
        """~1 at end without complete suffix is not ARQ."""
        assert parse_envelope("OK ~1") is None

    def test_version_2_ignored_when_checking(self):
        """A future version should parse but the app checks version."""
        env = parse_envelope("HI ~2D7Q2M9C")
        assert env is not None
        assert env.version == 2  # Parser returns it; caller filters

    def test_case_insensitivity(self):
        env = parse_envelope("hi ~1d7q2m9c")
        assert env is not None
        assert env.opcode == "D"
        assert env.message_id == "7Q2M9C"

    def test_payload_with_space_before_suffix(self):
        env = parse_envelope("HELLO WORLD  ~1DABCDEF")
        assert env is not None
        assert env.payload == "HELLO WORLD"

    def test_empty_string_returns_none(self):
        assert parse_envelope("") is None

    def test_none_value_returns_none(self):
        assert parse_envelope(None) is None

    def test_integer_value_returns_none(self):
        assert parse_envelope(42) is None


# ── Message ID generation ────────────────────────────────────────────────


class TestMessageId:
    def test_is_six_characters(self):
        mid = new_message_id()
        assert len(mid) == 6

    def test_only_crockford_base32(self):
        mid = new_message_id()
        alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
        assert all(c in alphabet for c in mid)

    def test_uniqueness(self):
        """Generate many IDs and verify no collisions."""
        ids = {new_message_id() for _ in range(1000)}
        assert len(ids) == 1000


# ── Timeout values ───────────────────────────────────────────────────────


class TestAckTimeouts:
    def test_mode_aware_ordering(self):
        assert ack_timeout_seconds("Turbo") < ack_timeout_seconds("Normal")
        assert ack_timeout_seconds("Fast") < ack_timeout_seconds("Slow")
        assert ack_timeout_seconds("Normal") < ack_timeout_seconds("JS8 40")
        assert ack_timeout_seconds("Slow") < ack_timeout_seconds("JS8 60")

    def test_fast_and_turbo_same_timeout(self):
        assert ack_timeout_seconds("Fast") == ack_timeout_seconds("Turbo")

    def test_unknown_mode_defaults_to_normal(self):
        assert ack_timeout_seconds(None) == ack_timeout_seconds("Normal")
        assert ack_timeout_seconds("BLAH") == ack_timeout_seconds("Normal")

    def test_all_modes_return_positive(self):
        for mode in ("Fast", "Turbo", "Normal", "Slow", "JS8 40", "JS8 60"):
            assert ack_timeout_seconds(mode) > 0


# ── ARQ Receipt deduplication (database) ─────────────────────────────────


class TestArqReceiptDedup:
    async def test_first_receipt_creates_row(self, db_session: AsyncSession, fixed_message_id: str):
        receipt = ArqReceipt(
            callsign="PA3ABC",
            protocol_version=ARQ_VERSION,
            protocol_id=fixed_message_id,
        )
        db_session.add(receipt)
        await db_session.commit()

        result = await db_session.scalar(
            select(ArqReceipt).where(
                ArqReceipt.callsign == "PA3ABC",
                ArqReceipt.protocol_version == ARQ_VERSION,
                ArqReceipt.protocol_id == fixed_message_id,
            )
        )
        assert result is not None
        assert result.duplicate_count == 0
        assert result.ack_sent_at is None

    async def test_duplicate_increments_counter(self, db_session: AsyncSession, fixed_message_id: str):
        receipt = ArqReceipt(
            callsign="PA3ABC",
            protocol_version=ARQ_VERSION,
            protocol_id=fixed_message_id,
            duplicate_count=1,
        )
        db_session.add(receipt)
        await db_session.flush()

        # Simulate duplicate arrival
        receipt.duplicate_count += 1
        receipt.last_received_at = datetime.now(UTC)
        await db_session.commit()

        result = await db_session.scalar(
            select(ArqReceipt).where(
                ArqReceipt.callsign == "PA3ABC",
                ArqReceipt.protocol_version == ARQ_VERSION,
                ArqReceipt.protocol_id == fixed_message_id,
            )
        )
        assert result is not None
        assert result.duplicate_count == 2

    async def test_different_callsign_same_id_not_duplicate(
        self, db_session: AsyncSession, fixed_message_id: str
    ):
        """Same message ID from different callsigns are independent receipts."""
        receipt_a = ArqReceipt(
            callsign="PA3ABC",
            protocol_version=ARQ_VERSION,
            protocol_id=fixed_message_id,
        )
        receipt_b = ArqReceipt(
            callsign="DL1XYZ",
            protocol_version=ARQ_VERSION,
            protocol_id=fixed_message_id,
        )
        db_session.add_all([receipt_a, receipt_b])
        await db_session.commit()

        results = (await db_session.scalars(
            select(ArqReceipt).where(ArqReceipt.protocol_id == fixed_message_id)
        )).all()
        assert len(results) == 2
        assert {r.callsign for r in results} == {"PA3ABC", "DL1XYZ"}

    async def test_unique_constraint_enforced(self, db_session: AsyncSession, fixed_message_id: str):
        """Cannot insert two receipts with same (callsign, version, id)."""
        r1 = ArqReceipt(
            callsign="PA3ABC",
            protocol_version=ARQ_VERSION,
            protocol_id=fixed_message_id,
        )
        r2 = ArqReceipt(
            callsign="PA3ABC",
            protocol_version=ARQ_VERSION,
            protocol_id=fixed_message_id,
        )
        db_session.add(r1)
        await db_session.commit()
        db_session.add(r2)
        with pytest.raises(Exception):  # noqa: B017 — sqlite3.IntegrityError wrapped by SQLAlchemy
            await db_session.commit()


# ── ACK marking on receipts ──────────────────────────────────────────────


class TestArqAckMarking:
    async def test_ack_sent_at_is_set(self, db_session: AsyncSession, fixed_message_id: str):
        receipt = ArqReceipt(
            callsign="PA3ABC",
            protocol_version=ARQ_VERSION,
            protocol_id=fixed_message_id,
        )
        db_session.add(receipt)
        await db_session.commit()

        now_ts = datetime.now(UTC)
        receipt.ack_sent_at = now_ts
        await db_session.commit()

        result = await db_session.scalar(
            select(ArqReceipt).where(
                ArqReceipt.callsign == "PA3ABC",
                ArqReceipt.protocol_version == ARQ_VERSION,
                ArqReceipt.protocol_id == fixed_message_id,
            )
        )
        assert result is not None
        assert result.ack_sent_at is not None
        assert abs((result.ack_sent_at - now_ts).total_seconds()) < 1

    async def test_ack_not_sent_when_not_yet_set(self, db_session: AsyncSession, fixed_message_id: str):
        receipt = ArqReceipt(
            callsign="PA3ABC",
            protocol_version=ARQ_VERSION,
            protocol_id=fixed_message_id,
        )
        db_session.add(receipt)
        await db_session.commit()

        result = await db_session.scalar(
            select(ArqReceipt).where(
                ArqReceipt.callsign == "PA3ABC",
                ArqReceipt.protocol_version == ARQ_VERSION,
                ArqReceipt.protocol_id == fixed_message_id,
            )
        )
        assert result is not None
        assert result.ack_sent_at is None


# ── Delivery state machine (database) ────────────────────────────────────


class TestDeliveryStateMachine:
    async def _create_confirmed_delivery(
        self, db_session: AsyncSession, callsign: str = "PA3ABC", protocol_id: str = "7Q2M9C"
    ) -> TransmittedMessage:
        tx = TransmittedMessage(
            callsign=callsign,
            text="Hello World",
            delivery_mode="confirmed",
            protocol_id=protocol_id,
            delivery_status="awaiting_ack",
            status="awaiting_ack",
            attempts=1,
            max_attempts=3,
            ack_deadline=datetime.now(UTC) + timedelta(seconds=60),
        )
        db_session.add(tx)
        await db_session.commit()
        return tx

    async def test_initial_state_is_awaiting_ack(self, db_session: AsyncSession):
        tx = await self._create_confirmed_delivery(db_session)
        assert tx.delivery_status == "awaiting_ack"
        assert tx.attempts == 1
        assert tx.ack_deadline is not None

    async def test_ack_marks_delivered(self, db_session: AsyncSession):
        tx = await self._create_confirmed_delivery(db_session)
        now_ts = datetime.now(UTC)

        tx.status = "delivered"
        tx.delivery_status = "delivered"
        tx.delivered_at = now_ts
        tx.confirmed_at = now_ts
        tx.ack_deadline = None
        await db_session.commit()

        result = await db_session.scalar(
            select(TransmittedMessage).where(TransmittedMessage.id == tx.id)
        )
        assert result is not None
        assert result.delivery_status == "delivered"
        assert result.delivered_at is not None

    async def test_timeout_marks_failed_when_max_attempts(self, db_session: AsyncSession):
        tx = TransmittedMessage(
            callsign="PA3ABC",
            text="Hello",
            delivery_mode="confirmed",
            protocol_id="7Q2M9C",
            delivery_status="retrying",
            status="retrying",
            attempts=3,
            max_attempts=3,
            ack_deadline=None,
        )
        db_session.add(tx)
        await db_session.commit()

        # Simulate the scheduler marking it failed
        tx.status = "failed"
        tx.delivery_status = "failed"
        tx.last_error = "No acknowledgement received"
        await db_session.commit()

        result = await db_session.scalar(
            select(TransmittedMessage).where(TransmittedMessage.id == tx.id)
        )
        assert result.delivery_status == "failed"

    async def test_retry_increments_attempt(self, db_session: AsyncSession):
        tx = await self._create_confirmed_delivery(db_session)

        tx.attempts += 1
        tx.delivery_status = "retrying"
        tx.status = "retrying"
        await db_session.commit()

        result = await db_session.scalar(
            select(TransmittedMessage).where(TransmittedMessage.id == tx.id)
        )
        assert result.attempts == 2
        assert result.delivery_status == "retrying"

    async def test_deadline_push_when_disconnected(self, db_session: AsyncSession):
        """When JS8Call is disconnected, deadline should be pushed forward."""
        # Set initial deadline in the PAST (expired) so the push-forward check is meaningful.
        old_deadline = datetime.now(UTC) - timedelta(seconds=10)
        tx = TransmittedMessage(
            callsign="PA3ABC",
            text="Hello",
            delivery_mode="confirmed",
            protocol_id="7Q2M9C",
            delivery_status="awaiting_ack",
            status="awaiting_ack",
            attempts=1,
            max_attempts=3,
            ack_deadline=old_deadline,
        )
        db_session.add(tx)
        await db_session.commit()

        # Simulate disconnected behavior: push deadline forward by 15s
        new_deadline = datetime.now(UTC) + timedelta(seconds=15)
        tx.ack_deadline = new_deadline
        await db_session.commit()

        result = await db_session.scalar(
            select(TransmittedMessage).where(TransmittedMessage.id == tx.id)
        )
        assert result.ack_deadline is not None
        assert result.ack_deadline > old_deadline

    async def test_best_effort_not_picked_up_by_scheduler(self, db_session: AsyncSession):
        """Best-effort messages should not be queried by the ARQ scheduler."""
        tx = TransmittedMessage(
            callsign="PA3ABC",
            text="Hello",
            delivery_mode="best_effort",
            protocol_id=None,
            delivery_status="sent",
            status="sent",
            attempts=1,
            max_attempts=1,
        )
        db_session.add(tx)
        await db_session.commit()

        # ARQ scheduler query filters on delivery_mode == "confirmed"
        results = (await db_session.scalars(
            select(TransmittedMessage).where(
                TransmittedMessage.delivery_mode == "confirmed",
                TransmittedMessage.delivery_status.in_(("awaiting_ack", "retrying")),
            )
        )).all()
        assert len(results) == 0


# ── Concurrent delivery constraint ───────────────────────────────────────


class TestConcurrentDeliveryConstraint:
    async def test_one_inflight_per_peer_allowed(self, db_session: AsyncSession):
        """The sender enforces at most one unacknowledged delivery per peer."""
        tx = TransmittedMessage(
            callsign="PA3ABC",
            text="Msg 1",
            delivery_mode="confirmed",
            protocol_id="111111",
            delivery_status="awaiting_ack",
            status="awaiting_ack",
            attempts=1,
            max_attempts=3,
            ack_deadline=datetime.now(UTC) + timedelta(seconds=60),
        )
        db_session.add(tx)
        await db_session.commit()

        # Query the same check that send_message uses
        active = await db_session.scalar(
            select(TransmittedMessage).where(
                TransmittedMessage.callsign == "PA3ABC",
                TransmittedMessage.delivery_mode == "confirmed",
                TransmittedMessage.delivery_status.in_(
                    ("transmitting", "awaiting_ack", "retrying")
                ),
            )
        )
        assert active is not None  # Would block a new delivery

    async def test_different_peers_no_conflict(self, db_session: AsyncSession):
        """Deliveries to different peers do not block each other."""
        for peer, pid in [("PA3ABC", "111111"), ("DL1XYZ", "222222")]:
            db_session.add(TransmittedMessage(
                callsign=peer,
                text="Msg",
                delivery_mode="confirmed",
                protocol_id=pid,
                delivery_status="awaiting_ack",
                status="awaiting_ack",
                attempts=1,
                max_attempts=3,
                ack_deadline=datetime.now(UTC) + timedelta(seconds=60),
            ))
        await db_session.commit()

        # Check PA3ABC — should only see its own delivery
        active = await db_session.scalar(
            select(TransmittedMessage).where(
                TransmittedMessage.callsign == "PA3ABC",
                TransmittedMessage.delivery_mode == "confirmed",
                TransmittedMessage.delivery_status.in_(
                    ("transmitting", "awaiting_ack", "retrying")
                ),
            )
        )
        assert active is not None
        assert active.callsign == "PA3ABC"

    async def test_delivered_does_not_block_new(self, db_session: AsyncSession):
        """A delivered message should NOT block a new confirmed delivery."""
        tx = TransmittedMessage(
            callsign="PA3ABC",
            text="Old",
            delivery_mode="confirmed",
            protocol_id="111111",
            delivery_status="delivered",
            status="delivered",
            attempts=1,
            max_attempts=3,
        )
        db_session.add(tx)
        await db_session.commit()

        active = await db_session.scalar(
            select(TransmittedMessage).where(
                TransmittedMessage.callsign == "PA3ABC",
                TransmittedMessage.delivery_mode == "confirmed",
                TransmittedMessage.delivery_status.in_(
                    ("transmitting", "awaiting_ack", "retrying")
                ),
            )
        )
        assert active is None  # Does NOT block


# ── Received messages with ARQ fields ────────────────────────────────────


class TestReceivedMessageArqFields:
    async def test_confirmed_message_stores_protocol_id(self, db_session: AsyncSession):
        msg = ReceivedMessage(
            callsign="PA3ABC",
            text="Hello",
            delivery_mode="confirmed",
            protocol_id="7Q2M9C",
        )
        db_session.add(msg)
        await db_session.commit()

        result = await db_session.scalar(
            select(ReceivedMessage).where(ReceivedMessage.protocol_id == "7Q2M9C")
        )
        assert result is not None
        assert result.delivery_mode == "confirmed"

    async def test_best_effort_has_null_protocol_id(self, db_session: AsyncSession):
        msg = ReceivedMessage(
            callsign="PA3ABC",
            text="Hello",
            delivery_mode="best_effort",
            protocol_id=None,
        )
        db_session.add(msg)
        await db_session.commit()

        result = await db_session.scalar(
            select(ReceivedMessage).where(ReceivedMessage.callsign == "PA3ABC")
        )
        assert result is not None
        assert result.protocol_id is None


# ── Ack deadline mode-aware calculation ──────────────────────────────────


class TestAckDeadlineCalculation:
    def test_fast_mode_deadline_is_45_seconds(self):
        deadline = ack_timeout_seconds("Fast")
        assert deadline == 45

    @pytest.mark.parametrize("mode,expected", [
        ("Turbo", 45),
        ("Fast", 45),
        ("Normal", 60),
        ("Slow", 120),
        ("JS8 40", 150),
        ("JS8 60", 210),
    ])
    def test_all_known_modes(self, mode: str, expected: int):
        assert ack_timeout_seconds(mode) == expected
