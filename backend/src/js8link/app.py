# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
import asyncio
import json
import logging
import os
import platform
import re
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import and_, delete, desc, func, or_, select
from sqlalchemy import exc as sa_exc
from sqlalchemy.ext.asyncio import AsyncSession

from . import __version__
from .config import get_settings
from .db import SessionLocal, get_session
from .domain.arq import ARQ_VERSION, ack_timeout_seconds, encode_ack, encode_data, new_message_id, parse_envelope
from .domain.changelog import load_changelog
from .domain.frequency_presets import FREQUENCY_PRESETS
from .domain.js8_protocol import describe_api_message, interpret_air_message
from .domain.maidenhead import great_circle_distance_km, grid_to_coordinates, try_grid_to_coordinates
from .domain.modes import mode_from_speed
from .domain.monitor import (
    classify_received_traffic,
    event_timestamp,
    extract_activity_sender_and_text,
    extract_sender_and_text,
    heartbeat_frame_text,
    is_heartbeat,
    normalize_monitor_text,
    parse_activity_sender_target,
)
from .domain.offsets import available_offsets, best_offset
from .domain.prefixes import callsign_location
from .domain.queries import infer_query_command, parse_query_response, query_spacing_seconds
from .domain.radio import band_from_frequency
from .domain.updates import (
    UpdateError,
    current_git_commit,
    get_github_branch,
    get_github_releases,
    git_output,
    normalize_github_repository,
    origin_github_repository,
    parse_version,
    platform_artifact_names,
    tracked_changes,
    validate_branch,
)
from .help import load_catalog
from .js8call import JS8CallClient, JS8CallError
from .models import (
    ActivityEvent,
    AppConfig,
    ArqReceipt,
    AuthConfig,
    ChatReadState,
    DiagnosticProcessing,
    DiagnosticTrace,
    JS8APIMessage,
    ReceivedMessage,
    Station,
    StationLink,
    StationQuery,
    TransmittedMessage,
)
from .schemas import (
    AboutResponse,
    AuthRequest,
    AutoreplyConfirmRequest,
    BandActivityResponse,
    BoolToggleRequest,
    CallActivityResponse,
    CallSelectedRequest,
    CallSelectedResponse,
    ChatSpeedPatch,
    ConfigPatch,
    ConfigResponse,
    ConnectionRequest,
    DiagnosticTraceDetailResponse,
    DiagnosticTraceListResponse,
    EventEnvelope,
    FilterEnabledRequest,
    FilterPatch,
    FilterResponse,
    FrequencyRequest,
    GroupsRequest,
    HbIntervalRequest,
    HealthResponse,
    HelpCatalogResponse,
    InboxStoreRequest,
    JS8SettingsPatch,
    MapPreferencesPatch,
    MessageRequest,
    OSResponse,
    PreferencesResponse,
    PTTResponse,
    PurgeResponse,
    SendMessageResponse,
    SetupRequest,
    SetupStatusResponse,
    SpeedRequest,
    SpotRequest,
    StationContactPatch,
    StationQueryRequest,
    StatusResponse,
    TuneRequest,
    TxQueueResponse,
    TxTextRequest,
    TxTextResponse,
    UIPreferencesPatch,
)

logger = logging.getLogger(__name__)
ph = PasswordHasher()


def now() -> datetime:
    """Return a timezone-naive UTC timestamp for SQLite datetime columns."""
    return datetime.now(UTC).replace(tzinfo=None)


def utcnow() -> datetime:
    """Return the current UTC time as a naive datetime.

    SQLite timestamps stored via ``server_default=func.now()`` (UTC) and
    ``event_timestamp``/``utc_timestamp`` fields are all UTC-naive.  Use this
    everywhere a ``received_at``/``utc_timestamp`` value is compared against
    "now" so the comparison stays in the same timezone as the stored data.
    """
    return now()


def utc_naive(value: datetime | None) -> datetime | None:
    """Normalize a timestamp before writing it to a SQLite datetime column."""
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


async def _repair_legacy_local_timestamps(session: AsyncSession) -> None:
    """Repair timestamps written by the old local-time helper.

    The former ``now = datetime.now`` helper stored local wall-clock time in
    columns that are otherwise UTC-naive. Only values that are still in the
    future and fall within the current local UTC offset are adjusted, making
    this repair safe and idempotent.
    """
    # Derive the local UTC offset from the difference between local wall-clock
    # time and UTC.  Works on all Python versions without relying on
    # astimezone()-on-naive behaviour.
    local_offset = datetime.now() - datetime.now(UTC).replace(tzinfo=None)
    if not local_offset or local_offset <= timedelta(0):
        return
    current = utcnow()
    upper_bound = current + local_offset + timedelta(minutes=5)
    station_fields = (
        "first_seen",
        "last_seen",
        "last_snr_query_at",
        "last_hearing_query_at",
        "last_info_query_at",
        "last_grid_query_at",
        "last_status_query_at",
        "hearing_updated_at",
        "info_updated_at",
        "status_updated_at",
    )
    stations = (await session.scalars(select(Station))).all()
    for station in stations:
        for field in station_fields:
            value = getattr(station, field)
            if value is not None and current < value <= upper_bound:
                setattr(station, field, value - local_offset)

    chat_states = (await session.scalars(select(ChatReadState))).all()
    for state in chat_states:
        if state.last_read_at is not None and current < state.last_read_at <= upper_bound:
            state.last_read_at -= local_offset
    await session.commit()


async def _repair_legacy_monitor_records(session: AsyncSession) -> None:
    """Remove monitor rows created from pre-classification API snapshots.

    Older releases stored snapshot traffic as lowercase ``rx`` (and activity
    rows as ``rx.activity``).  Those rows have no trustworthy event identity:
    every refresh could give the same decoded text a new ``received_at``.  It
    is safer to discard them than to present a false recent reception.
    """
    await session.execute(
        delete(ReceivedMessage).where(
            or_(
                ReceivedMessage.message_type == "rx",
                ReceivedMessage.message_type == "rx.activity",
                ReceivedMessage.sender_source == "offset_inferred",
            )
        )
    )
    stale_snapshots = (
        await session.scalars(
            select(ReceivedMessage).where(ReceivedMessage.message_type == "RX.BAND_ACTIVITY")
        )
    ).all()
    for message in stale_snapshots:
        if (
            message.received_at is not None
            and message.utc_timestamp is not None
            and message.received_at > message.utc_timestamp + timedelta(minutes=15)
        ):
            await session.delete(message)

    stations = (await session.scalars(select(Station))).all()
    for station in stations:
        latest = await session.scalar(
            select(func.max(func.coalesce(ReceivedMessage.utc_timestamp, ReceivedMessage.received_at))).where(
                or_(
                    ReceivedMessage.callsign == station.callsign,
                    ReceivedMessage.from_callsign == station.callsign,
                )
            )
        )
        if latest is not None:
            station.last_seen = latest
    await session.commit()


async def _restore_chat_on_activity(session: AsyncSession, callsign: str | None) -> None:
    """Make an archived conversation visible again when it becomes active."""
    normalized = (callsign or "").strip().upper()
    if not normalized:
        return
    state = await session.scalar(select(ChatReadState).where(ChatReadState.callsign == normalized))
    if state is not None and state.archived:
        state.archived = False


settings = get_settings()

app = FastAPI(title="JS8Link", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------
client: JS8CallClient | None = None
local_callsign: str | None = None
tx_busy: bool = False
rx_enabled: bool = True
tx_enabled: bool = True
transmit_locks: dict[str, asyncio.Lock] = {}
connected_websockets: set[WebSocket] = set()
update_lock = asyncio.Lock()
api_message_write_lock = asyncio.Lock()
diagnostic_write_lock = asyncio.Lock()
tx_state: dict[str, Any] = {}
band_activity_snapshot_cache: tuple[datetime, dict[str, Any]] | None = None
band_activity_snapshot_lock = asyncio.Lock()
RX_DATA_EVENTS = frozenset(
    {
        "RX.ACTIVITY",
        "RX.BAND_ACTIVITY",
        "RX.DIRECTED",
        "RX.SPOT",
        "RX.CALL_ACTIVITY",
        "RX.TEXT",
    }
)

PROJECT_ROOT = (
    Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parents[3]
)

_HEARTBEAT_INTERVAL = timedelta(minutes=15)
# A TX.FRAME and its decoded RX event can arrive a few seconds apart. Keep
# this window short so a later, genuinely repeated heartbeat is not hidden.
_TRANSMITTED_FRAME_DEDUP_WINDOW = timedelta(seconds=5)
_HEARTBEAT_RESPONSE_HINT_WINDOW = timedelta(seconds=30)


def _queue_heartbeat_response_hint(source: str | None, received_snr: object) -> None:
    """Remember the text of JS8Call's possible tone-only auto-response."""
    if not local_callsign or not source or received_snr is None:
        return
    if not isinstance(received_snr, (int, str)) or isinstance(received_snr, bool):
        return
    try:
        snr = int(received_snr)
    except ValueError:
        return
    tx_state["pending_heartbeat_response"] = {
        "text": f"{local_callsign} {source} HEARTBEAT SNR {snr:+03d}",
        "queued_at": utcnow(),
    }
_BAND_ACTIVITY_CACHE_TTL = timedelta(seconds=30)


async def _get_band_activity_snapshot() -> dict[str, Any]:
    """Share short-lived band snapshots between concurrent API consumers."""
    global band_activity_snapshot_cache
    current = utcnow()
    if (
        band_activity_snapshot_cache is not None
        and current - band_activity_snapshot_cache[0] < _BAND_ACTIVITY_CACHE_TTL
    ):
        return band_activity_snapshot_cache[1]

    async with band_activity_snapshot_lock:
        current = utcnow()
        if (
            band_activity_snapshot_cache is not None
            and current - band_activity_snapshot_cache[0] < _BAND_ACTIVITY_CACHE_TTL
        ):
            return band_activity_snapshot_cache[1]
        if not client or not client.connected:
            raise JS8CallError("JS8Call not connected")
        snapshot = await client.request("RX.GET_BAND_ACTIVITY")
        band_activity_snapshot_cache = (current, snapshot)
        return snapshot


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
async def _get_auth_config(session: AsyncSession) -> AuthConfig:
    result = await session.scalars(select(AuthConfig).where(AuthConfig.id == 1))
    config = result.one_or_none()
    if config is None:
        config = AuthConfig(id=1)
        session.add(config)
        await session.commit()
        await session.refresh(config)
    return config


async def _verify_password(session: AsyncSession, password: str) -> bool:
    auth = await _get_auth_config(session)
    if not auth.enabled or not auth.password_hash:
        return True
    try:
        ph.verify(auth.password_hash, password)
        return True
    except VerificationError:
        return False


# ---------------------------------------------------------------------------
# Broadcast helper
# ---------------------------------------------------------------------------
async def broadcast(event: str, data: dict[str, Any]) -> None:
    if event != "diagnostics.trace":
        await _record_diagnostic_trace(
            source="websocket",
            event_type=event,
            summary="WebSocket event sent",
            interpretation=f"JS8Link sent the {event} event to connected web clients.",
            raw_payload=data,
            processing=[
                (
                    "WebSocket output",
                    "sent",
                    "The typed event envelope was sent to connected web clients.",
                    {"event": event},
                )
            ],
        )
    envelope = EventEnvelope(event=event, data=data, timestamp=now())
    payload = envelope.model_dump(mode="json")
    disconnected: list[WebSocket] = []
    for ws in connected_websockets.copy():
        try:
            await ws.send_json(payload)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        connected_websockets.discard(ws)


_DIAGNOSTIC_SECRET_KEYS = frozenset({"password", "password_hash", "token", "authorization"})


def _diagnostic_json(value: Any) -> str:
    """Create readable, stable diagnostic data without leaking credentials."""
    def sanitize(item: Any, key: str | None = None) -> Any:
        if key and key.lower() in _DIAGNOSTIC_SECRET_KEYS:
            return "[redacted]"
        if isinstance(item, dict):
            return {str(name): sanitize(content, str(name)) for name, content in item.items()}
        if isinstance(item, list):
            return [sanitize(content) for content in item]
        if isinstance(item, tuple):
            return [sanitize(content) for content in item]
        if isinstance(item, datetime):
            normalized = utc_naive(item)
            return normalized.isoformat() if normalized is not None else None
        return item

    return json.dumps(sanitize(value), ensure_ascii=False, indent=2, default=str, sort_keys=True)


def _diagnostic_snr(value: object) -> str:
    """Format an external SNR value without allowing malformed input to break diagnostics."""
    try:
        numeric = float(str(value).strip())
    except (TypeError, ValueError):
        return str(value)
    if numeric.is_integer():
        return f"{int(numeric):+03d}"
    return f"{numeric:+.1f}"


def _describe_js8_message(message: dict[str, Any], is_response: bool) -> tuple[str, str]:
    """Translate an API envelope using the central protocol interpreter."""
    meaning = describe_api_message(message, is_response=is_response)
    return meaning.summary, meaning.interpretation


async def _record_diagnostic_trace(
    *,
    source: str,
    event_type: str,
    summary: str,
    interpretation: str,
    raw_payload: Any | None = None,
    severity: str = "info",
    processing: list[tuple[str, str, str, Any | None]] | None = None,
) -> str | None:
    """Persist one structured trace and announce it to live diagnostic views."""
    trace_id = str(uuid4())
    async with diagnostic_write_lock:
        try:
            async with SessionLocal() as session:
                config = await _get_app_config(session)
                if not config.diagnostics_enabled:
                    return None
                trace = DiagnosticTrace(
                    trace_id=trace_id,
                    source=source,
                    event_type=event_type,
                    severity=severity,
                    summary=summary,
                    raw_payload=_diagnostic_json(raw_payload) if raw_payload is not None else None,
                    interpretation=interpretation,
                )
                session.add(trace)
                for sequence, (operation, outcome, detail, payload) in enumerate(processing or [], start=1):
                    session.add(
                        DiagnosticProcessing(
                            trace_id=trace_id,
                            sequence=sequence,
                            operation=operation,
                            outcome=outcome,
                            detail=detail,
                            payload=_diagnostic_json(payload) if payload is not None else None,
                        )
                    )
                await session.commit()
        except Exception:
            logger.exception("Failed to persist diagnostic trace")
            return None
    await broadcast("diagnostics.trace", {"trace_id": trace_id, "source": source, "event_type": event_type})
    return trace_id


async def _append_diagnostic_processing(
    trace_id: str | None,
    operation: str,
    detail: str,
    *,
    outcome: str = "ok",
    payload: Any | None = None,
) -> None:
    if not trace_id:
        return
    async with diagnostic_write_lock:
        try:
            async with SessionLocal() as session:
                trace = await session.scalar(select(DiagnosticTrace).where(DiagnosticTrace.trace_id == trace_id))
                if trace is None:
                    return
                sequence = (
                    await session.scalar(
                        select(func.max(DiagnosticProcessing.sequence)).where(
                            DiagnosticProcessing.trace_id == trace_id
                        )
                    )
                    or 0
                )
                session.add(
                    DiagnosticProcessing(
                        trace_id=trace_id,
                        sequence=sequence + 1,
                        operation=operation,
                        outcome=outcome,
                        detail=detail,
                        payload=_diagnostic_json(payload) if payload is not None else None,
                    )
                )
                await session.commit()
        except Exception:
            logger.exception("Failed to append diagnostic processing")


def _diagnostic_http_payload(raw: bytes, *, content_type: str | None = None) -> Any:
    """Decode a bounded HTTP body for the raw diagnostics layer."""
    if not raw:
        return None
    truncated = len(raw) > 100_000
    body = raw[:100_000].decode("utf-8", errors="replace")
    if content_type and "json" in content_type:
        try:
            value: Any = json.loads(body)
        except json.JSONDecodeError:
            value = body
    else:
        value = body
    return {"value": value, "truncated": truncated} if truncated else value


def _describe_http_action(method: str, path: str, status_code: int) -> tuple[str, str]:
    """Create an operator-readable interpretation of an application API call."""
    action = f"{method} {path}"
    if status_code >= 500:
        return "Application action failed", f"The application action {action} failed with HTTP {status_code}."
    if status_code >= 400:
        return "Application request rejected", f"The application rejected {action} with HTTP {status_code}."
    return "Application action completed", f"The application completed {action} with HTTP {status_code}."


class DiagnosticHTTPMiddleware:
    """Capture every API request and response without consuming its body."""

    def __init__(self, application: Any) -> None:
        self.application = application

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or not str(scope.get("path", "")).startswith("/api/"):
            await self.application(scope, receive, send)
            return
        if str(scope.get("path", "")).startswith("/api/diagnostics/"):
            await self.application(scope, receive, send)
            return

        request_chunks: list[bytes] = []
        response_chunks: list[bytes] = []
        status_code = 500
        response_content_type: str | None = None

        async def diagnostic_receive() -> dict[str, Any]:
            message = await receive()
            if message.get("type") == "http.request":
                request_chunks.append(message.get("body", b""))
            return message

        async def diagnostic_send(message: dict[str, Any]) -> None:
            nonlocal status_code, response_content_type
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", 500))
                headers = dict(message.get("headers", []))
                response_content_type = headers.get(b"content-type", b"").decode("latin-1")
            elif message.get("type") == "http.response.body":
                response_chunks.append(message.get("body", b""))
            await send(message)

        method = str(scope.get("method", "GET"))
        path = str(scope.get("path", ""))
        query = bytes(scope.get("query_string", b"")).decode("latin-1")
        try:
            await self.application(scope, diagnostic_receive, diagnostic_send)
        except Exception as error:
            summary, interpretation = _describe_http_action(method, path, 500)
            await _record_diagnostic_trace(
                source="user_action" if method not in {"GET", "HEAD", "OPTIONS"} else "http_api",
                event_type=f"HTTP.{method} {path}"[:128],
                summary=summary,
                interpretation=f"{interpretation} Error: {error}",
                raw_payload={
                    "request": {
                        "method": method,
                        "path": path,
                        "query": query,
                        "body": _diagnostic_http_payload(b"".join(request_chunks)),
                    }
                },
                severity="error",
                processing=[("HTTP request", "failed", str(error), {"status_code": 500})],
            )
            raise
        else:
            summary, interpretation = _describe_http_action(method, path, status_code)
            await _record_diagnostic_trace(
                source="user_action" if method not in {"GET", "HEAD", "OPTIONS"} else "http_api",
                event_type=f"HTTP.{method} {path}"[:128],
                summary=summary,
                interpretation=interpretation,
                raw_payload={
                    "request": {
                        "method": method,
                        "path": path,
                        "query": query,
                        "body": _diagnostic_http_payload(b"".join(request_chunks)),
                    },
                    "response": _diagnostic_http_payload(
                        b"".join(response_chunks), content_type=response_content_type
                    ),
                },
                severity="error" if status_code >= 400 else "info",
                processing=[
                    (
                        "HTTP response",
                        "failed" if status_code >= 400 else "ok",
                        f"The application returned HTTP {status_code}.",
                        {"status_code": status_code},
                    )
                ],
            )


app.add_middleware(DiagnosticHTTPMiddleware)


# ---------------------------------------------------------------------------
# transmit_js8_text (per-peer locking)
# ---------------------------------------------------------------------------
async def transmit_js8_text(
    js8_client: JS8CallClient,
    text: str,
    *,
    peer: str | None = None,
) -> None:
    if not tx_enabled:
        raise JS8CallError("TX is disabled")
    lock = transmit_locks.setdefault(peer or "__global__", asyncio.Lock())
    async with lock:
        await js8_client.send("TX.SEND_MESSAGE", text)


async def wait_for_tx_buffer_empty(js8_client: JS8CallClient, *, timeout: float = 300.0) -> None:
    """Wait until JS8Call's editable TX buffer is empty before changing callsign."""
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        info = await js8_client.request("TX.GET_TEXT")
        if not str(info.get("value") or "").strip():
            return
        if asyncio.get_running_loop().time() >= deadline:
            raise JS8CallError("TX buffer remained filled while waiting to change callsign")
        await asyncio.sleep(0.25)


# ---------------------------------------------------------------------------
# send_arq_ack
# ---------------------------------------------------------------------------
async def send_arq_ack(
    js8_client: JS8CallClient,
    callsign: str,
    protocol_version: int,
    protocol_id: str,
    received_message_id: int,
) -> None:
    """Send an ARQ acknowledgement for a received data message.

    The DB write is performed *after* transmission so ``ack_sent_at``
    is only set when the ACK actually went on air.  Sending a duplicate
    ACK is harmless per the ARQ specification.
    """
    # Transmit first
    try:
        await transmit_js8_text(
            js8_client,
            f"{callsign} {encode_ack(protocol_id)}",
            peer=callsign,
        )
    except Exception:
        logger.exception(
            "Failed to transmit ARQ acknowledgement to %s for %s",
            callsign,
            protocol_id,
        )
        return

    # Record in DB after successful transmission
    try:
        async with SessionLocal() as session:
            result = await session.scalars(
                select(ArqReceipt).where(
                    ArqReceipt.callsign == callsign,
                    ArqReceipt.protocol_version == protocol_version,
                    ArqReceipt.protocol_id == protocol_id,
                )
            )
            receipt = result.one_or_none()
            now_ts = now()
            if receipt is None:
                receipt = ArqReceipt(
                    callsign=callsign,
                    protocol_version=protocol_version,
                    protocol_id=protocol_id,
                    received_message_id=received_message_id,
                    ack_sent_at=now_ts,
                )
                session.add(receipt)
            else:
                receipt.ack_sent_at = now_ts
                receipt.last_received_at = now_ts
                receipt.received_message_id = received_message_id
            await session.commit()
    except sa_exc.IntegrityError:
        logger.warning(
            "Duplicate ARQ receipt record for %s (%s) — receipt already exists",
            callsign,
            protocol_id,
        )
    except Exception:
        logger.exception(
            "Failed to record ARQ acknowledgement for %s (%s)",
            callsign,
            protocol_id,
        )


# ---------------------------------------------------------------------------
# Event handler: on_js8_event
# ---------------------------------------------------------------------------
async def _process_js8_event(message: dict[str, Any]) -> None:
    global local_callsign, tx_busy

    message_type = (message.get("type") or "").upper()
    params = message.get("params") or {}
    value = str(message.get("value") or "")
    trace_id = message.get("_js8link_diagnostic_trace_id")

    # JS8Call's automatic heartbeat responses can emit a TX.FRAME containing
    # only tone data. Carry forward the latest radio metadata so that frame
    # still belongs to the correct band in the monitor.
    for key in ("DIAL", "OFFSET", "SPEED"):
        if params.get(key) is not None:
            tx_state[f"last_{key.lower()}"] = params[key]

    # Keep the raw API trace even when RX processing is disabled, but record
    # the explicit decision not to turn the decode into application data.
    if not rx_enabled and message_type in RX_DATA_EVENTS:
        await _append_diagnostic_processing(
            trace_id,
            "RX processing skipped",
            "Incoming JS8Call traffic was received, but application RX processing is disabled.",
            outcome="skipped",
        )
        return

    if message_type in RX_DATA_EVENTS:
        await broadcast(
            event="radio.rx",
            data={
                "type": message_type,
                "offset": params.get("OFFSET"),
                "snr": params.get("SNR"),
            },
        )

    if message_type in ("RX.ACTIVITY", "RX.BAND_ACTIVITY"):
        await _handle_activity(message, message_type, params, value)
        await _append_diagnostic_processing(
            trace_id,
            "Monitor traffic persisted",
            "The decoded band traffic was classified, deduplicated and stored for the Band Monitor.",
        )
        return

    if message_type == "RX.DIRECTED":
        await _handle_directed(message, params, value)
        await _append_diagnostic_processing(
            trace_id,
            "Directed traffic processed",
            "The directed frame was classified and any matching station, chat or query records were updated.",
        )
        return

    if message_type == "TX.FRAME":
        await _handle_tx_frame(message, params, value)
        await _append_diagnostic_processing(
            trace_id,
            "Transmit frame recorded",
            "The transmitted frame was recorded with its available radio metadata.",
        )
        return

    if message_type == "STATION.CLOSING":
        reason = str(params.get("REASON", "unknown"))
        logger.info("JS8Call is closing: %s", reason)
        await broadcast(
            event="js8call.closing",
            data={"reason": reason},
        )
        await _append_diagnostic_processing(
            trace_id,
            "Connection state updated",
            "JS8Call closing state was broadcast to connected clients.",
        )
        return

    if message_type == "API.ERROR":
        error_text = str(value or params.get("value", "")).strip()
        logger.warning("JS8Call API error: %s", error_text or "(no detail)")
        await broadcast(
            event="js8call.error",
            data={"error": error_text, "raw": message},
        )
        await _append_diagnostic_processing(
            trace_id,
            "JS8Call API error received",
            f"JS8Call rejected an API request with error: {error_text or 'no detail provided'}.",
        )
        return

    if message_type == "RIG.PTT":
        ptt_state = params.get("PTT")
        tx_busy = bool(ptt_state)
        tx_state["active"] = bool(ptt_state)
        if not ptt_state:
            tx_state["message"] = ""
            tx_state["frames_sent"] = 0
        await broadcast(
            event="radio.ptt",
            data={
                "ptt": tx_busy,
                "message": str(params.get("MESSAGE", "")),
                "utc": params.get("UTC"),
            },
        )
        if tx_busy:
            await broadcast(
                event="tx.progress",
                data={
                    "state": "started",
                    "message": tx_state.get("message", ""),
                    "estimated_frames": tx_state.get("estimated_frames", 1),
                },
            )
        else:
            await broadcast(
                event="tx.progress",
                data={
                    "state": "completed",
                },
            )
        await _append_diagnostic_processing(
            trace_id,
            "PTT state processed",
            "The radio transmit state was broadcast to connected clients.",
        )
        return

    if message_type == "RX.SPOT":
        spot_call = str(params.get("CALL", "") or "").strip().upper()
        spot_grid = str(params.get("GRID", "") or "").strip().upper()
        async with SessionLocal() as session:
            if spot_call:
                await _upsert_station_from_event(
                    session,
                    callsign=spot_call,
                    snr=params.get("SNR"),
                    frequency=params.get("DIAL"),
                    offset=params.get("OFFSET"),
                    mode=mode_from_speed(params.get("SPEED")),
                )
                if spot_grid and len(spot_grid) >= 4:
                    station = await session.scalar(
                        select(Station).where(Station.callsign == spot_call)
                    )
                    if station is not None and (
                        station.grid is None or station.grid_source != "query"
                    ):
                        station.grid = spot_grid
                        station.grid_source = "spot"
                        try:
                            lat, lon = grid_to_coordinates(spot_grid)
                            station.latitude = lat
                            station.longitude = lon
                        except ValueError:
                            pass
        await broadcast(
            event="radio.spot",
            data={
                "call": params.get("CALL"),
                "grid": params.get("GRID"),
                "snr": params.get("SNR"),
                "dial": params.get("DIAL"),
                "offset": params.get("OFFSET"),
            },
        )
        await _append_diagnostic_processing(
            trace_id,
            "Station spot processed",
            "The spotted station data was applied to the station record and broadcast to clients.",
        )
        return


async def on_js8_event(message: dict[str, Any]) -> None:
    """Process an incoming JS8Call event and diagnose processing failures."""
    trace_id = message.get("_js8link_diagnostic_trace_id")
    try:
        await _process_js8_event(message)
    except Exception as error:
        await _append_diagnostic_processing(
            trace_id,
            "Event processing failed",
            "The incoming JS8Call event could not be processed by JS8Link.",
            outcome="failed",
            payload={"error": str(error)},
        )
        raise


# ---------------------------------------------------------------------------
async def _handle_activity(
    message: dict[str, Any],
    message_type: str,
    params: dict[str, Any],
    value: str,
) -> None:
    entries = _band_activity_entries(message_type, params, value)
    broadcasts: list[dict[str, Any]] = []
    trace_id = message.get("_js8link_diagnostic_trace_id")

    for entry_params, raw in entries:
        entry_ts = event_timestamp({"params": entry_params})
        air_meaning = interpret_air_message(raw, entry_params)
        await _append_diagnostic_processing(
            trace_id,
            air_meaning.summary,
            air_meaning.interpretation,
            payload={
                "kind": air_meaning.kind,
                "source": air_meaning.source,
                "target": air_meaning.target,
                "command": air_meaning.command,
                "reported_snr": air_meaning.snr,
                "received_snr": entry_params.get("SNR"),
                "offset": entry_params.get("OFFSET"),
            },
        )
        # RX.BAND_ACTIVITY is a snapshot when requested through the API.  A
        # snapshot can contain decodes from many hours ago; treating those as
        # a new reception makes station last-heard data incorrect.  Only a
        # recently timestamped decode is reliable enough for monitor history
        # and station discovery.
        #
        # The stale check uses a UTC-naive datetime for comparison with
        # utcnow(), but the timestamp passed to downstream handlers must stay
        # timezone-aware so _find_received_frame_duplicate can normalise it
        # correctly (astimezone() on a naive datetime misinterprets it as
        # local time, shifting by the system offset and breaking dedup).
        if entry_ts.tzinfo is not None:
            entry_ts_naive = entry_ts.astimezone(UTC).replace(tzinfo=None)
        else:
            entry_ts_naive = entry_ts
        if entry_ts_naive < utcnow() - timedelta(minutes=15):
            logger.debug("Ignoring stale %s activity at %s", message_type, entry_ts)
            await _append_diagnostic_processing(
                trace_id,
                "Activity entry skipped",
                "This snapshot entry is older than 15 minutes and was not treated as a new reception.",
                outcome="skipped",
                payload={"event_timestamp": entry_ts.isoformat()},
            )
            continue
        if air_meaning.kind == "heartbeat_report" and air_meaning.target:
            source = air_meaning.source
            target = air_meaning.target
            # Our own heartbeat going out (we are the reporter): record as TX.
            # We must also guard against source being None for band-activity
            # entries that lack the CALLSIGN: prefix.
            if local_callsign and source and source == local_callsign.upper():
                async with SessionLocal() as session:
                    frame_text = heartbeat_frame_text(source, target, raw)
                    duplicate = await session.scalar(
                        select(TransmittedMessage).where(
                            TransmittedMessage.text == frame_text,
                            TransmittedMessage.transmitted_at >= utcnow() - _TRANSMITTED_FRAME_DEDUP_WINDOW,
                        )
                    )
                    if duplicate is None:
                        _raw_off = entry_params.get("OFFSET")
                        session.add(
                            TransmittedMessage(
                                callsign=local_callsign,
                                text=frame_text,
                                status="sent",
                                delivery_mode="best_effort",
                                tx_frame_type="TX.FRAME",
                                is_heartbeat=True,
                                band=band_from_frequency(entry_params.get("DIAL")),
                                offset=int(_raw_off) if _raw_off is not None else None,
                                mode=mode_from_speed(entry_params.get("SPEED")),
                            )
                        )
                        await session.commit()
                if duplicate is None:
                    await _broadcast_monitor_tx_frame(frame_text, entry_params)
                continue
            # Someone reporting about us — or source unknown (band activity):
            # process normally as received traffic.
            if source is not None:
                await _record_band_activity_heartbeat(
                    source,
                    target,
                    air_meaning.snr,
                    entry_params,
                    entry_ts,
                    offset=entry_params.get("OFFSET"),
                )
            continue
        if air_meaning.kind == "heartbeat_beacon" and air_meaning.source:
            if local_callsign and air_meaning.source == local_callsign.upper():
                async with SessionLocal() as session:
                    frame_text = normalize_monitor_text(raw)
                    duplicate = await session.scalar(
                        select(TransmittedMessage).where(
                            TransmittedMessage.text == frame_text,
                            TransmittedMessage.transmitted_at >= utcnow() - _TRANSMITTED_FRAME_DEDUP_WINDOW,
                        )
                    )
                    if duplicate is None:
                        _raw_off = entry_params.get("OFFSET")
                        session.add(
                            TransmittedMessage(
                                callsign=local_callsign,
                                text=frame_text,
                                status="sent",
                                delivery_mode="best_effort",
                                tx_frame_type="TX.FRAME",
                                is_heartbeat=True,
                                band=band_from_frequency(entry_params.get("DIAL")),
                                offset=int(_raw_off) if _raw_off is not None else None,
                                mode=mode_from_speed(entry_params.get("SPEED")),
                            )
                        )
                        await session.commit()
                if duplicate is None:
                    await _broadcast_monitor_tx_frame(frame_text, entry_params)
                continue
            await _record_band_activity_heartbeat_beacon(
                air_meaning.source,
                air_meaning.grid,
                entry_params,
                entry_ts,
                offset=entry_params.get("OFFSET"),
            )
            continue

        sender, activity_text = extract_activity_sender_and_text(raw)
        sender = (
            str(entry_params.get("CALL") or entry_params.get("FROM") or entry_params.get("CALLSIGN") or sender or "")
            .strip()
            .upper()
            or None
        )
        # JS8Call can decode its own transmitted frames as RX.ACTIVITY.
        # Convert those into TransmittedMessage rows so the monitor shows
        # them as TX traffic (auto-replies, heartbeat ACKs, UI messages).
        #
        # Band-activity entries without the CALLSIGN: prefix can misidentify
        # the target of a heartbeat report as the sender ("PE1PUX HEARTBEAT
        # SNR -10").  Skip those — they are reports ABOUT us, not FROM us.
        if sender and local_callsign and sender == local_callsign.upper():
            normalized = normalize_monitor_text(activity_text)
            if "HEARTBEAT" in normalized.upper():
                frame_text = heartbeat_frame_text(sender, None, normalized)
                async with SessionLocal() as session:
                    duplicate = await session.scalar(
                        select(TransmittedMessage).where(
                            TransmittedMessage.text == frame_text,
                            TransmittedMessage.transmitted_at >= utcnow() - _TRANSMITTED_FRAME_DEDUP_WINDOW,
                        )
                    )
                    if duplicate is None:
                        session.add(
                            TransmittedMessage(
                                callsign=local_callsign,
                                text=frame_text,
                                status="sent",
                                delivery_mode="best_effort",
                                tx_frame_type="TX.FRAME",
                                is_heartbeat=True,
                                band=band_from_frequency(entry_params.get("DIAL")),
                                offset=int(entry_params["OFFSET"])
                                if entry_params.get("OFFSET") is not None
                                else None,
                                mode=mode_from_speed(entry_params.get("SPEED")),
                            )
                        )
                        await session.commit()
                if duplicate is None:
                    await _broadcast_monitor_tx_frame(frame_text, entry_params)
                continue
            async with SessionLocal() as session:
                duplicate = await session.scalar(
                    select(TransmittedMessage).where(
                        TransmittedMessage.text == normalize_monitor_text(activity_text),
                        TransmittedMessage.transmitted_at >= utcnow() - _TRANSMITTED_FRAME_DEDUP_WINDOW,
                    )
                )
                if duplicate is None:
                    _raw_off = entry_params.get("OFFSET")
                    session.add(
                        TransmittedMessage(
                            callsign=local_callsign,
                            text=normalize_monitor_text(activity_text),
                            status="sent",
                            delivery_mode="best_effort",
                            tx_frame_type="TX.FRAME",
                            band=band_from_frequency(entry_params.get("DIAL")),
                            offset=int(_raw_off) if _raw_off is not None else None,
                            mode=mode_from_speed(entry_params.get("SPEED")),
                        )
                    )
                    await session.commit()
            continue
        normalized = normalize_monitor_text(activity_text)
        # Skip completely empty decodes — nothing useful to store or display.
        if not normalized and not sender:
            continue
        async with SessionLocal() as session:
            activity = ActivityEvent(
                event_type=message_type.lower(),
                payload=raw,
            )
            session.add(activity)

            entry = ReceivedMessage(
                callsign=sender,
                sender_source="parsed" if sender else raw,
                text=normalized,
                kind=classify_received_traffic(message_type),
                delivery_mode="best_effort",
                message_type=message_type,
                frequency=entry_params.get("DIAL"),
                offset=entry_params.get("OFFSET"),
                band=band_from_frequency(entry_params.get("DIAL")),
                mode=mode_from_speed(entry_params.get("SPEED")),
                snr=entry_params.get("SNR"),
                tdrift=entry_params.get("TDRIFT"),
                utc_timestamp=utc_naive(entry_ts),
                raw_payload=raw,
            )
            duplicate = await _find_received_frame_duplicate(
                session,
                sender=sender,
                text=normalized,
                timestamp=entry_ts,
                offset=entry.offset,
                snr=entry.snr,
            )
            if duplicate is not None:
                _merge_received_frame(duplicate, entry)
                await session.commit()
                continue
            session.add(entry)
            await session.flush()

            message_id = entry.id
            message_received_at = entry.utc_timestamp

            # Station discovery from band activity uses the same parser as the
            # stored sender, so colon and space-separated JS8Call snapshots are
            # handled consistently.
            if sender:
                await _upsert_station_from_event(
                    session,
                    callsign=sender,
                    snr=entry_params.get("SNR"),
                    frequency=entry_params.get("DIAL"),
                    offset=entry_params.get("OFFSET"),
                    mode=mode_from_speed(entry_params.get("SPEED")),
                    tdrift=entry_params.get("TDRIFT"),
                    observed_at=entry_ts,
                )

            # Passive link discovery: when band-activity shows traffic between
            # two other stations (SOURCE: TARGET ...), record the target station
            # and a link between them.  This builds the station graph without
            # needing active queries to every station.
            link_info = parse_activity_sender_target(raw)
            if link_info and sender:
                link_source, link_target, _link_remainder = link_info
                if link_source.upper() == sender.upper() and link_target != sender.upper():
                    target_station = await session.scalar(
                        select(Station).where(Station.callsign == link_target)
                    )
                    if target_station is None:
                        location = callsign_location(link_target)
                        target_station = Station(
                            callsign=link_target,
                            grid=None,
                            latitude=location.latitude if location else None,
                            longitude=location.longitude if location else None,
                            country=location.country if location else None,
                            location_source="prefix" if location else None,
                            first_seen=utc_naive(entry_ts) or now(),
                            last_seen=None,
                            last_snr=None,
                            message_count=0,
                        )
                        session.add(target_station)
                        await session.flush()
                    source_station = await session.scalar(
                        select(Station).where(Station.callsign == sender.upper())
                    )
                    if source_station and target_station:
                        await _update_station_link(
                            session,
                            source_station_id=source_station.id,
                            target_station_id=target_station.id,
                            relation_type="observed",
                            snr=entry_params.get("SNR"),
                            band=band_from_frequency(entry_params.get("DIAL")),
                        )

            await session.commit()
        # Build rich broadcast data so the frontend can prepend messages
        # directly without a full API reload.
        is_dup = bool(duplicate)
        broadcast_id = None if is_dup else message_id
        broadcast_ts = (
            message_received_at.isoformat()
            if not is_dup and message_received_at
            else None
        )
        broadcasts.append(
            {
                "id": broadcast_id,
                "type": message_type.lower(),
                "sender": sender,
                "text": normalized,
                "snr": entry_params.get("SNR"),
                "dial": entry_params.get("DIAL"),
                "offset": entry_params.get("OFFSET"),
                "speed": entry_params.get("SPEED"),
                "mode": mode_from_speed(entry_params.get("SPEED")),
                "band": band_from_frequency(entry_params.get("DIAL")),
                "received_at": broadcast_ts,
                "is_duplicate": is_dup,
            }
        )

    for broadcast_data in broadcasts:
        await broadcast(event="activity.received", data=broadcast_data)


async def _broadcast_monitor_tx_frame(text: str, params: dict[str, Any]) -> None:
    """Make locally echoed heartbeat transmissions visible immediately."""
    await broadcast(
        event="radio.tx_frame",
        data={
            "text": text,
            "dial": params.get("DIAL"),
            "offset": params.get("OFFSET"),
            "band": band_from_frequency(params.get("DIAL")),
            "mode": mode_from_speed(params.get("SPEED")),
        },
    )


async def _find_received_frame_duplicate(
    session: AsyncSession,
    *,
    sender: str | None,
    text: str,
    timestamp: datetime,
    offset: object,
    snr: object,
    heartbeat: bool = False,
) -> ReceivedMessage | None:
    """Find one radio frame reported through two JS8Call event routes."""
    if not text:
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    else:
        timestamp = timestamp.astimezone(UTC)
    timestamp = timestamp.replace(tzinfo=None)

    base: list = [
        ReceivedMessage.utc_timestamp.between(
            timestamp - timedelta(seconds=2), timestamp + timedelta(seconds=2)
        ),
    ]
    if sender:
        base.append(
            or_(ReceivedMessage.callsign == sender, ReceivedMessage.from_callsign == sender)
        )
    else:
        # Unknown sender — match only other unknown-sender entries so we
        # don't accidentally dedup against a known station's message.
        base.append(
            and_(ReceivedMessage.callsign.is_(None), ReceivedMessage.from_callsign.is_(None))
        )
    if heartbeat:
        base.append(ReceivedMessage.is_heartbeat.is_(True))
    if offset is not None:
        base.append(or_(ReceivedMessage.offset == offset, ReceivedMessage.offset.is_(None)))
    if snr is not None:
        base.append(or_(ReceivedMessage.snr == snr, ReceivedMessage.snr.is_(None)))

    # Phase 1: exact text match.
    conditions = base + [ReceivedMessage.text == text]
    result = await session.scalar(select(ReceivedMessage).where(*conditions).limit(1))
    if result is not None:
        return result

    # Phase 2 (heartbeat only): loose text match.  One event path may add
    # a grid locator suffix, producing "CALL @HB HEARTBEAT" vs
    # "CALL @HB HEARTBEAT IO91".  Match when one is a prefix of the other.
    if heartbeat and text:
        candidates = (
            await session.scalars(select(ReceivedMessage).where(*base).limit(5))
        ).all()
        for candidate in candidates:
            candidate_text = candidate.text or ""
            if candidate_text.startswith(text) or text.startswith(candidate_text):
                return candidate

    return None


def _merge_received_frame(existing: ReceivedMessage, incoming: ReceivedMessage) -> None:
    """Keep the richer directed representation when event routes overlap."""
    if existing.message_type != "RX.DIRECTED" and incoming.message_type == "RX.DIRECTED":
        existing.message_type = incoming.message_type
        existing.kind = incoming.kind
        existing.sender_source = incoming.sender_source
        existing.from_callsign = incoming.from_callsign
        existing.to_callsign = incoming.to_callsign
        existing.command = incoming.command
        if incoming.delivery_mode is not None:
            existing.delivery_mode = incoming.delivery_mode
        existing.raw_payload = incoming.raw_payload
    if existing.callsign is None:
        existing.callsign = incoming.callsign
    if existing.offset is None:
        existing.offset = incoming.offset
    if existing.snr is None:
        existing.snr = incoming.snr
    if existing.utc_timestamp is None:
        existing.utc_timestamp = incoming.utc_timestamp
    # Upgrade text to the richer version (e.g. heartbeat with grid locator).
    if incoming.text and len(incoming.text) > len(existing.text or ""):
        existing.text = incoming.text


def _band_activity_entries(
    message_type: str,
    params: dict[str, Any],
    value: str,
) -> list[tuple[dict[str, Any], str]]:
    """Expand JS8Call's RX.BAND_ACTIVITY offset map into monitor records."""
    if message_type == "RX.BAND_ACTIVITY":
        entries: list[tuple[dict[str, Any], str]] = []
        for key, payload in params.items():
            if key.startswith("_") or not isinstance(payload, dict):
                continue
            if payload.get("OFFSET") is None:
                continue
            entries.append(({**params, **payload}, str(payload.get("TEXT") or value).strip()))
        if entries:
            return entries
    return [(params, value.strip())]


# ---------------------------------------------------------------------------
async def _record_band_activity_heartbeat(
    source: str,
    target: str,
    reported_snr: int | None,
    params: dict[str, Any],
    ts: datetime,
    offset: object = None,
) -> None:
    if not local_callsign:
        return
    # A heartbeat contains two different signal reports:
    # - the SNR in the text is the reporting station's observation of target;
    # - params.SNR is the SNR with which our radio received this frame.
    # They describe different directions and must never be interchanged.
    received_snr = params.get("SNR")
    if reported_snr is not None:
        body = f"{target} HEARTBEAT SNR {reported_snr:+03d}"
    else:
        body = f"{target} HEARTBEAT"
    frame_text = heartbeat_frame_text(source, target, body)
    async with SessionLocal() as session:
        duplicate = await _find_received_frame_duplicate(
            session,
            sender=source,
            text=frame_text,
            timestamp=ts,
            offset=offset,
            snr=received_snr,
            heartbeat=True,
        )
        if duplicate is not None:
            return
        entry = ReceivedMessage(
            callsign=source,
            text=frame_text,
            kind="heartbeat",
            delivery_mode="best_effort",
            message_type="RX.BAND_ACTIVITY",
            is_heartbeat=True,
            frequency=params.get("DIAL"),
            offset=offset,
            band=band_from_frequency(params.get("DIAL")),
            mode=mode_from_speed(params.get("SPEED")),
            snr=received_snr,
            from_callsign=source,
            to_callsign=target,
            utc_timestamp=utc_naive(ts),
        )
        session.add(entry)

        source_station = await _upsert_station(
            session,
            source,
            snr=received_snr,
            frequency=params.get("DIAL"),
            offset=offset,
            mode=mode_from_speed(params.get("SPEED")),
            observed_at=ts,
        )
        target_station = await session.scalar(select(Station).where(Station.callsign == target))
        if target_station is None and not target.startswith("@"):
            location = callsign_location(target)
            target_station = Station(
                callsign=target,
                grid=None,
                latitude=location.latitude if location else None,
                longitude=location.longitude if location else None,
                country=location.country if location else None,
                location_source="prefix" if location else None,
                first_seen=utc_naive(ts),
                last_seen=None,
                last_snr=None,
                message_count=0,
            )
            session.add(target_station)
            await session.flush()
        if source_station and target_station and not target.startswith("@"):
            await _update_station_link(
                session,
                source_station_id=source_station.id,
                target_station_id=target_station.id,
                relation_type="heartbeat",
                snr=reported_snr,
                band=band_from_frequency(params.get("DIAL")),
            )
        await session.commit()


# ---------------------------------------------------------------------------
async def _record_band_activity_heartbeat_beacon(
    source: str,
    grid: str | None,
    params: dict[str, Any],
    ts: datetime,
    offset: object = None,
) -> None:
    """Store an @HB announcement without inventing a station-to-@HB link."""

    body = f"@HB HEARTBEAT{f' {grid}' if grid else ''}"
    frame_text = heartbeat_frame_text(source, "@HB", body)
    _queue_heartbeat_response_hint(source, params.get("SNR"))
    async with SessionLocal() as session:
        duplicate = await _find_received_frame_duplicate(
            session,
            sender=source,
            text=frame_text,
            timestamp=ts,
            offset=offset,
            snr=params.get("SNR"),
            heartbeat=True,
        )
        if duplicate is not None:
            return
        session.add(
            ReceivedMessage(
                callsign=source,
                text=frame_text,
                kind="heartbeat",
                delivery_mode="best_effort",
                message_type="RX.BAND_ACTIVITY",
                is_heartbeat=True,
                frequency=params.get("DIAL"),
                offset=offset,
                band=band_from_frequency(params.get("DIAL")),
                mode=mode_from_speed(params.get("SPEED")),
                snr=params.get("SNR"),
                from_callsign=source,
                to_callsign="@HB",
                utc_timestamp=utc_naive(ts),
            )
        )
        station = await _upsert_station(
            session,
            source,
            snr=params.get("SNR"),
            frequency=params.get("DIAL"),
            offset=offset,
            mode=mode_from_speed(params.get("SPEED")),
            observed_at=ts,
        )
        if station is not None and grid and (station.grid is None or station.grid_source != "query"):
            station.grid = grid
            station.grid_source = station.grid_source or "heartbeat"
            try:
                station.latitude, station.longitude = grid_to_coordinates(grid)
            except ValueError:
                pass
        await session.commit()


# ---------------------------------------------------------------------------
# Query response parser
# ---------------------------------------------------------------------------
async def _handle_query_response(
    session: AsyncSession,
    callsign: str,
    command: str,
    body: str,
    params: dict[str, Any],
) -> bool:
    """Parse and store query response data from a directed message."""
    parsed = parse_query_response(command, body)
    if parsed is None:
        return False

    result = await session.scalars(select(Station).where(Station.callsign == callsign))
    station = result.one_or_none()
    if station is None:
        return False

    now_ts = now()

    if command == "SNR":
        if parsed.snr is None:
            return False
        station.last_snr = parsed.snr
        station.last_snr_query_at = now_ts
        await _mark_query_responded(session, station.id, "snr", body, snr_value=parsed.snr)

    elif command == "HEARING":
        hearing_entries = [dict(entry) for entry in parsed.hearing]
        for entry in hearing_entries:
            heard_call = str(entry["callsign"])
            heard_snr = int(entry["snr"])
            heard_station = await _upsert_station(
                session,
                heard_call,
                snr=heard_snr,
                frequency=params.get("DIAL"),
                offset=params.get("OFFSET"),
                mode=mode_from_speed(params.get("SPEED")),
            )
            if heard_station and station.id != heard_station.id:
                await session.flush()
                await _update_station_link(
                    session,
                    source_station_id=station.id,
                    target_station_id=heard_station.id,
                    relation_type="hearing",
                    snr=heard_snr,
                    band=band_from_frequency(params.get("DIAL")),
                )
        station.hearing_report = json.dumps(hearing_entries)
        station.hearing_updated_at = now_ts
        station.last_hearing_query_at = now_ts
        await _mark_query_responded(session, station.id, "hearing", body, hearing_data=hearing_entries)

    elif command == "INFO":
        if parsed.text is None:
            return False
        station.info_text = parsed.text
        station.info_updated_at = now_ts
        station.last_info_query_at = now_ts
        await _mark_query_responded(session, station.id, "info", body)

    elif command == "GRID":
        if parsed.grid is None:
            return False
        grid_val = parsed.grid
        station.grid = grid_val
        station.grid_source = "query"
        station.last_grid_query_at = now_ts
        from .domain.maidenhead import grid_to_coordinates

        try:
            lat, lon = grid_to_coordinates(grid_val)
            station.latitude = lat
            station.longitude = lon
        except ValueError:
            pass
        await _mark_query_responded(session, station.id, "grid", body)

    elif command == "STATUS":
        if parsed.text is None:
            return False
        station.status_text = parsed.text
        station.status_updated_at = now_ts
        station.last_status_query_at = now_ts
        await _mark_query_responded(session, station.id, "status", body)

    elif command == "MSGS":
        station.last_hearing_query_at = now_ts
        await _mark_query_responded(
            session, station.id, "msgs", body,
            hearing_data=[{"id": mid} for mid in parsed.msg_ids],
        )

    elif command == "MSG":
        if parsed.text is None:
            return False
        # Response to QUERY MSG <id> — the body is the stored message.
        await _mark_query_responded(session, station.id, "msg", body)

    return True


async def _mark_query_responded(
    session: AsyncSession,
    station_id: int,
    query_type: str,
    response_text: str,
    *,
    snr_value: int | None = None,
    hearing_data: list[dict[str, Any]] | None = None,
) -> None:
    """Mark the most recent pending query for this station/type as responded."""
    result = await session.scalars(
        select(StationQuery)
        .where(
            StationQuery.station_id == station_id,
            StationQuery.query_type == query_type,
            StationQuery.status == "pending",
        )
        .order_by(desc(StationQuery.requested_at))
        .limit(1)
    )
    query = result.one_or_none()
    if query is not None:
        query.status = "responded"
        query.responded_at = now()
        query.response_text = response_text
        if snr_value is not None:
            query.snr_value = snr_value
        if hearing_data is not None:
            query.hearing_data = json.dumps(hearing_data)


# ---------------------------------------------------------------------------
async def _handle_directed(
    message: dict[str, Any],
    params: dict[str, Any],
    value: str,
) -> None:
    ts = event_timestamp(message)
    raw = value.strip()
    sender, body = extract_sender_and_text(raw)
    if sender is None:
        candidate = str(params.get("FROM") or "").strip().upper()
        if candidate:
            sender = candidate
            body = raw
    # Normalize body for consistent deduplication with RX.ACTIVITY handler.
    body = normalize_monitor_text(body)
    command = str(params.get("CMD") or "").strip().upper()

    if is_heartbeat(message):
        is_local_transmission = bool(
            local_callsign and sender and sender.upper() == local_callsign.upper()
        )
        await _handle_directed_heartbeat(sender, body, params, ts)
        # Notify monitor clients after the heartbeat has been persisted.
        await broadcast(
            event="radio.tx_frame" if is_local_transmission else "activity.received",
            data={
                "type": "TX.FRAME" if is_local_transmission else "rx.directed",
                "value": body,
                "text": heartbeat_frame_text(sender, interpret_air_message(raw, params).target, body),
                "sender": sender,
                "snr": params.get("SNR"),
                "dial": params.get("DIAL"),
                "offset": params.get("OFFSET"),
                "speed": params.get("SPEED"),
                "band": band_from_frequency(params.get("DIAL")),
                "mode": mode_from_speed(params.get("SPEED")),
            },
        )
        return

    # Strip the target callsign if it appears at the beginning of the body.
    # JS8Call renders directed messages as "SOURCE: TARGET text"; after the
    # sender prefix is removed the target is still present.
    raw_to = str(params.get("TO", "") or "").strip().upper()
    if raw_to and body.upper().startswith(raw_to + " "):
        body = body[len(raw_to) + 1 :].strip()

    # JS8Call-improved usually labels a query reply as CMD=MSG. Infer the
    # actual query from the directed text and persist the reply as monitor
    # traffic as well as updating the station/query record.
    query_command = infer_query_command(command, body)
    # When the text doesn't match a known query pattern, check whether we
    # have a pending QUERY MSG for this station — the response to QUERY MSG
    # is the stored message text, which has no distinguishing format.
    if query_command is None and sender and body.strip():
        async with SessionLocal() as session:
            existing = await session.scalar(
                select(Station).where(Station.callsign == sender.upper())
            )
            if existing is not None:
                pending_msg = await session.scalar(
                    select(StationQuery).where(
                        StationQuery.station_id == existing.id,
                        StationQuery.query_type == "msg",
                        StationQuery.status == "pending",
                    )
                    .order_by(desc(StationQuery.requested_at))
                    .limit(1)
                )
                if pending_msg is not None:
                    query_command = "MSG"
    if query_command and sender:
        async with SessionLocal() as session:
            await _upsert_station_from_event(
                session,
                callsign=sender,
                snr=params.get("SNR"),
                frequency=params.get("DIAL"),
                offset=params.get("OFFSET"),
                mode=mode_from_speed(params.get("SPEED")),
                tdrift=params.get("TDRIFT"),
            )
            handled = await _handle_query_response(session, sender, query_command, body, params)
            if handled:
                entry = ReceivedMessage(
                    callsign=sender,
                    sender_source=raw,
                    kind="directed_control",
                    delivery_mode="best_effort",
                    text=normalize_monitor_text(body),
                    message_type="RX.DIRECTED",
                    frequency=params.get("DIAL"),
                    offset=params.get("OFFSET"),
                    band=band_from_frequency(params.get("DIAL")),
                    mode=mode_from_speed(params.get("SPEED")),
                    snr=params.get("SNR"),
                    tdrift=params.get("TDRIFT"),
                    from_callsign=sender,
                    to_callsign=local_callsign,
                    command=query_command,
                    utc_timestamp=utc_naive(ts),
                    raw_payload=raw,
                )
                duplicate = await _find_received_frame_duplicate(
                    session,
                    sender=sender,
                    text=normalize_monitor_text(body),
                    timestamp=ts,
                    offset=params.get("OFFSET"),
                    snr=params.get("SNR"),
                )
                if duplicate is not None:
                    _merge_received_frame(duplicate, entry)
                else:
                    session.add(entry)
            await session.commit()
            if handled:
                return

    # Determine whether this message was actually directed at our station.
    # Must happen BEFORE ARQ envelope detection — otherwise ARQ data for
    # other stations is stored as our chat message and we send a spurious ACK.
    raw_to = str(params.get("TO", "") or "").strip().upper()
    is_group = bool(raw_to.startswith("@")) if raw_to else False
    actual_target: str | None = None
    if raw_to and not is_group:
        actual_target = raw_to
    is_local = (
        not actual_target
        or (local_callsign is not None and actual_target == local_callsign.upper())
    )

    # ARQ envelope detection
    envelope = parse_envelope(body if sender else raw)

    async with SessionLocal() as session:
        if envelope is not None and is_local and not is_group:
            if envelope.opcode == "D":
                # Data message with ARQ suffix
                await _handle_arq_data(session, sender or "", envelope, params, ts, raw)
                await session.commit()
                return
            elif envelope.opcode == "A":
                # Acknowledgement
                await _handle_arq_ack(session, sender or "", envelope)
                await session.commit()
                return

        # When the message is not for us and there was no ARQ or query-response
        # work to do, stop here.
        if not is_local:
            return

        # Skip empty payloads from partial decodes — nothing useful to store.
        if not body.strip():
            return

        # Regular directed message (no ARQ, or unparseable) — for us by now.
        traffic_kind = classify_received_traffic("rx.directed", command=command)

        entry = ReceivedMessage(
            callsign=sender,
            sender_source=raw,
            kind=traffic_kind,
            text=body,
            delivery_mode="best_effort",
            message_type="RX.DIRECTED",
            frequency=params.get("DIAL"),
            offset=params.get("OFFSET"),
            band=band_from_frequency(params.get("DIAL")),
            mode=mode_from_speed(params.get("SPEED")),
            snr=params.get("SNR"),
            tdrift=params.get("TDRIFT"),
            from_callsign=sender,
            to_callsign=raw_to if is_group else (actual_target or local_callsign),
            command=command,
            utc_timestamp=utc_naive(ts),
            raw_payload=raw,
        )
        duplicate_was_activity = False
        duplicate = await _find_received_frame_duplicate(
            session,
            sender=sender,
            text=body,
            timestamp=ts,
            offset=params.get("OFFSET"),
            snr=params.get("SNR"),
        )
        if duplicate is not None:
            duplicate_was_activity = duplicate.message_type != "RX.DIRECTED"
            _merge_received_frame(duplicate, entry)
        else:
            session.add(entry)
        # Only interact with the chat system when the message was for us.
        if is_local:
            # For group-addressed messages, the chat is keyed on the group
            # (@HB, @ALLCALL, etc.) so all group traffic lands in one chat.
            chat_key = raw_to if is_group else sender
            if chat_key:
                await _restore_chat_on_activity(session, chat_key)
        if sender:
            await _upsert_station_from_event(
                session,
                callsign=sender,
                snr=params.get("SNR"),
                frequency=params.get("DIAL"),
                offset=params.get("OFFSET"),
                mode=mode_from_speed(params.get("SPEED")),
                tdrift=params.get("TDRIFT"),
            )
            directed_grid = str(params.get("GRID", "") or "").strip().upper()
            if directed_grid and len(directed_grid) >= 4:
                station = await session.scalar(
                    select(Station).where(Station.callsign == sender)
                )
                if station is not None and (
                    station.grid is None or station.grid_source != "query"
                ):
                    station.grid = directed_grid
                    if station.grid_source is None:
                        station.grid_source = "directed"
                    try:
                        lat, lon = grid_to_coordinates(directed_grid)
                        station.latitude = lat
                        station.longitude = lon
                    except ValueError:
                        pass
        await session.commit()

    if is_local and (duplicate is None or duplicate_was_activity) and (sender or is_group):
        chat_callsign = raw_to if is_group else sender
        await broadcast(
            event="chat.message.received",
            data={
                "id": entry.id if duplicate is None else None,
                "callsign": chat_callsign,
                "text": body,
                "command": command,
                "to_callsign": params.get("TO"),
                "from_callsign": sender,
                "intended_for_local": True,
                "snr": params.get("SNR"),
                "mode": mode_from_speed(params.get("SPEED")),
                "band": band_from_frequency(params.get("DIAL")),
                "offset": params.get("OFFSET"),
                "timestamp": ts.isoformat() if ts else now().isoformat(),
                "is_duplicate": duplicate is not None,
            },
        )


# ---------------------------------------------------------------------------
async def _handle_arq_data(
    session: AsyncSession,
    callsign: str,
    envelope: Any,
    params: dict[str, Any],
    ts: datetime,
    raw: str,
) -> None:
    """Process an incoming ARQ data message, de-duplicate, and send ACK."""
    # Check for existing receipt (de-duplication)
    result = await session.scalars(
        select(ArqReceipt).where(
            ArqReceipt.callsign == callsign,
            ArqReceipt.protocol_version == envelope.version,
            ArqReceipt.protocol_id == envelope.message_id,
        )
    )
    existing = result.one_or_none()
    received_message_id: int | None = None

    if existing is None:
        entry = ReceivedMessage(
            callsign=callsign,
            sender_source=raw,
            kind="direct_message",
            text=envelope.payload,
            delivery_mode="confirmed",
            protocol_id=envelope.message_id,
            message_type="RX.DIRECTED",
            frequency=params.get("DIAL"),
            offset=params.get("OFFSET"),
            band=band_from_frequency(params.get("DIAL")),
            mode=mode_from_speed(params.get("SPEED")),
            snr=params.get("SNR"),
            tdrift=params.get("TDRIFT"),
            from_callsign=callsign,
            to_callsign=local_callsign,
            utc_timestamp=utc_naive(ts),
            raw_payload=raw,
        )
        session.add(entry)
        await session.flush()
        received_message_id = entry.id
        await _restore_chat_on_activity(session, callsign)

        receipt = ArqReceipt(
            callsign=callsign,
            protocol_version=envelope.version,
            protocol_id=envelope.message_id,
            received_message_id=entry.id,
        )
        session.add(receipt)
    else:
        existing.duplicate_count += 1
        existing.last_received_at = now()
        received_message_id = existing.received_message_id

    if callsign:
        await _upsert_station_from_event(
            session,
            callsign=callsign,
            snr=params.get("SNR"),
            frequency=params.get("DIAL"),
            offset=params.get("OFFSET"),
            mode=mode_from_speed(params.get("SPEED")),
            tdrift=params.get("TDRIFT"),
        )

    # Commit before sending ACK so send_arq_ack can see the ArqReceipt
    await session.commit()

    # Send ACK if not already sent
    if existing is None or existing.ack_sent_at is None:
        if client and client.connected:
            if received_message_id is not None:
                await send_arq_ack(
                    client,
                    callsign,
                    envelope.version,
                    envelope.message_id,
                    received_message_id,
                )

    if callsign:
        await broadcast(
            event="chat.message.received",
            data={
                "callsign": callsign,
                "text": envelope.payload,
                "to_callsign": local_callsign,
                "intended_for_local": True,
                "protocol_id": envelope.message_id,
                "delivery_mode": "confirmed",
                "snr": params.get("SNR"),
                "mode": mode_from_speed(params.get("SPEED")),
                "duplicate": existing is not None and existing.ack_sent_at is not None,
                "timestamp": ts.isoformat() if ts else now().isoformat(),
            },
        )


# ---------------------------------------------------------------------------
async def _handle_arq_ack(
    session: AsyncSession,
    callsign: str,
    envelope: Any,
) -> None:
    """Process an incoming ARQ acknowledgement."""
    result = await session.scalars(
        select(TransmittedMessage).where(
            TransmittedMessage.callsign == callsign,
            TransmittedMessage.protocol_id == envelope.message_id,
            TransmittedMessage.protocol_version == envelope.version,
            TransmittedMessage.delivery_mode == "confirmed",
            TransmittedMessage.delivery_status.in_(("awaiting_ack", "retrying")),
        )
    )
    delivery = result.one_or_none()
    if delivery is None:
        return

    delivery.status = "delivered"
    delivery.delivery_status = "delivered"
    delivery.delivered_at = now()
    delivery.confirmed_at = now()
    delivery.ack_deadline = None

    await broadcast(
        event="chat.delivery.updated",
        data={
            "callsign": callsign,
            "protocol_id": envelope.message_id,
            "status": "delivered",
        },
    )


# ---------------------------------------------------------------------------
async def _handle_directed_heartbeat(
    sender: str | None,
    body: str,
    params: dict[str, Any],
    ts: datetime,
) -> None:
    display_text = f"{sender}: {body}" if sender else body
    meaning = interpret_air_message(display_text, params)
    target = meaning.target
    frame_text = heartbeat_frame_text(sender, target, body)
    if meaning.kind == "heartbeat_beacon" and sender and target == "@HB":
        _queue_heartbeat_response_hint(sender, params.get("SNR"))
    if local_callsign and sender and sender.upper() == local_callsign.upper():
        async with SessionLocal() as session:
            duplicate = await session.scalar(
                select(TransmittedMessage).where(
                    TransmittedMessage.text == frame_text,
                    TransmittedMessage.transmitted_at >= utcnow() - _TRANSMITTED_FRAME_DEDUP_WINDOW,
                )
            )
            if duplicate is None:
                session.add(
                    TransmittedMessage(
                        callsign=local_callsign,
                        text=frame_text,
                        status="sent",
                        delivery_mode="best_effort",
                        tx_frame_type="TX.FRAME",
                        is_heartbeat=True,
                        band=band_from_frequency(params.get("DIAL")),
                        offset=int(params["OFFSET"]) if params.get("OFFSET") is not None else None,
                        mode=mode_from_speed(params.get("SPEED")),
                    )
                )
                await session.commit()
        return
    async with SessionLocal() as session:
        duplicate = await _find_received_frame_duplicate(
            session,
            sender=sender,
            text=frame_text,
            timestamp=ts,
            offset=params.get("OFFSET"),
            snr=params.get("SNR"),
            heartbeat=True,
        )
        if duplicate is not None:
            return
        entry = ReceivedMessage(
            callsign=sender,
            text=frame_text,
            kind="heartbeat",
            delivery_mode="best_effort",
            message_type="RX.DIRECTED",
            is_heartbeat=True,
            frequency=params.get("DIAL"),
            offset=params.get("OFFSET"),
            band=band_from_frequency(params.get("DIAL")),
            mode=mode_from_speed(params.get("SPEED")),
            snr=params.get("SNR"),
            tdrift=params.get("TDRIFT"),
            from_callsign=sender,
            to_callsign=target,
            utc_timestamp=utc_naive(ts),
        )
        session.add(entry)
        if sender:
            source_station = await _upsert_station_from_event(
                session,
                callsign=sender,
                snr=params.get("SNR"),
                frequency=params.get("DIAL"),
                offset=params.get("OFFSET"),
                mode=mode_from_speed(params.get("SPEED")),
                tdrift=params.get("TDRIFT"),
            )
            # Only HEARTBEAT SNR is a report about another station.  An @HB
            # HEARTBEAT frame is a beacon/request and must not create a
            # fictional @HB station or relation.  params.SNR is solely our
            # local reception of the sender and is never substituted for a
            # missing reported SNR in the text.
            if (
                meaning.kind == "heartbeat_report"
                and meaning.snr is not None
                and target
                and not target.startswith("@")
                and target != sender
            ):
                target_station = await session.scalar(
                    select(Station).where(Station.callsign == target)
                )
                if target_station is None:
                    location = callsign_location(target)
                    target_station = Station(
                        callsign=target,
                        grid=None,
                        latitude=location.latitude if location else None,
                        longitude=location.longitude if location else None,
                        country=location.country if location else None,
                        location_source="prefix" if location else None,
                        first_seen=utc_naive(ts) or now(),
                        last_seen=None,
                        last_snr=None,
                        message_count=0,
                    )
                    session.add(target_station)
                    await session.flush()
                if source_station and target_station:
                    await _update_station_link(
                        session,
                        source_station_id=source_station.id,
                        target_station_id=target_station.id,
                        relation_type="heartbeat",
                        snr=meaning.snr,
                        band=band_from_frequency(params.get("DIAL")),
                    )
            # Extract grid from directed params (JS8Call v3.0+ includes GRID)
            directed_grid = meaning.grid or str(params.get("GRID", "") or "").strip().upper()
            if directed_grid and len(directed_grid) >= 4 and source_station is not None:
                if source_station.grid is None or source_station.grid_source != "query":
                    source_station.grid = directed_grid
                    if source_station.grid_source is None:
                        source_station.grid_source = "directed"
                    try:
                        lat, lon = grid_to_coordinates(directed_grid)
                        source_station.latitude = lat
                        source_station.longitude = lon
                    except ValueError:
                        pass
        await session.commit()


# ---------------------------------------------------------------------------
async def _handle_tx_frame(
    message: dict[str, Any],
    params: dict[str, Any],
    value: str,
) -> None:
    """Track transmitted frame metadata (band, offset, mode).

    For confirmed-delivery messages, transitions the delivery status
    from ``transmitting`` to ``awaiting_ack`` when the frame actually
    goes on air so the ack deadline starts from on-air time.
    """
    dial = params.get("DIAL") if params.get("DIAL") is not None else tx_state.get("last_dial")
    offset = params.get("OFFSET") if params.get("OFFSET") is not None else tx_state.get("last_offset")
    speed = params.get("SPEED") if params.get("SPEED") is not None else tx_state.get("last_speed")
    mode_val = mode_from_speed(speed)

    # Record every transmitted frame as monitor traffic.  JS8Link-initiated
    # messages also go through api_send_message which creates its own
    # TransmittedMessage row, so the 30-second duplicate check below prevents
    # double-counting regardless of whether tx_state["message"] was set yet.
    # Build meaningful frame text.  JS8Call may send the human-readable text
    # in ``value``, or raw tone symbols.  When ``value`` is empty or only
    # contains diamond markers, fall back to params.TEXT or a place-holder.
    frame_text = value.strip()
    if not frame_text or set(frame_text) <= {"♢", " "}:
        frame_text = str(params.get("TEXT", "") or "").strip()
    if not frame_text:
        pending_response = tx_state.get("pending_heartbeat_response") or tx_state.get(
            "pending_heartbeat_beacon"
        )
        if isinstance(pending_response, dict):
            queued_at = pending_response.get("queued_at")
            if isinstance(queued_at, datetime) and utcnow() - queued_at <= _HEARTBEAT_RESPONSE_HINT_WINDOW:
                frame_text = str(pending_response.get("text") or "")
            tx_state.pop("pending_heartbeat_response", None)
            tx_state.pop("pending_heartbeat_beacon", None)
        if not frame_text:
            frame_text = "(TX frame)"
    air_meaning = interpret_air_message(frame_text, params)
    frame_is_heartbeat = air_meaning.kind in {"heartbeat_beacon", "heartbeat_report"}
    if frame_text:
        async with SessionLocal() as session:
            duplicate = await session.scalar(
                select(TransmittedMessage).where(
                    TransmittedMessage.tx_frame_type == "TX.FRAME",
                    TransmittedMessage.text == frame_text,
                    TransmittedMessage.transmitted_at >= utcnow() - _TRANSMITTED_FRAME_DEDUP_WINDOW,
                )
            )
            if duplicate is None:
                session.add(
                    TransmittedMessage(
                        callsign=local_callsign,
                        text=frame_text,
                        status="sent",
                        delivery_mode="best_effort",
                        tx_frame_type="TX.FRAME",
                        is_heartbeat=frame_is_heartbeat,
                        band=band_from_frequency(dial),
                        offset=int(offset) if offset is not None else None,
                        mode=mode_val,
                    )
                )
                await session.commit()

    # Transition ARQ confirmed messages from "transmitting" to "awaiting_ack"
    envelope = parse_envelope(value)
    if envelope is not None and envelope.opcode == "D":
        async with SessionLocal() as session:
            result = await session.scalars(
                select(TransmittedMessage).where(
                    TransmittedMessage.delivery_mode == "confirmed",
                    TransmittedMessage.delivery_status == "transmitting",
                    TransmittedMessage.protocol_id == envelope.message_id,
                )
            )
            delivery = result.first()
            if delivery is not None:
                delivery.delivery_status = "awaiting_ack"
                delivery.ack_deadline = now() + timedelta(seconds=ack_timeout_seconds(mode_val))
                await session.commit()

    # Update tx_state frame counter
    tx_state["frames_sent"] = tx_state.get("frames_sent", 0) + 1
    tx_state["estimated_frames"] = tx_state.get("estimated_frames", 2)

    await broadcast(
        event="radio.tx_frame",
        data={
            "text": frame_text,
            "dial": dial,
            "offset": offset,
            "band": band_from_frequency(dial),
            "mode": mode_val,
            "speed": speed,
        },
    )

    await broadcast(
        event="tx.progress",
        data={
            "state": "frame",
            "frames_sent": tx_state.get("frames_sent", 0),
            "estimated_frames": tx_state.get("estimated_frames", 1),
            "progress_pct": min(
                int(tx_state.get("frames_sent", 0) / max(tx_state.get("estimated_frames", 1), 1) * 100),
                100,
            ),
        },
    )


# ---------------------------------------------------------------------------
async def on_js8_api_message(message: dict[str, Any], is_response: bool) -> None:
    """Persist every JS8Call API message for debugging."""
    message_type = str(message.get("type") or "").upper()
    params = message.get("params") or {}
    for key in ("DIAL", "OFFSET", "SPEED"):
        if params.get(key) is not None:
            tx_state[f"last_{key.lower()}"] = params[key]
    summary, interpretation = _describe_js8_message(message, is_response)
    trace_id = await _record_diagnostic_trace(
        source="js8_api",
        event_type=message_type or "UNKNOWN",
        summary=summary,
        interpretation=interpretation,
        raw_payload=message,
        processing=[
            (
                "JS8Call API input",
                "ok",
                "The raw JSON envelope was received from JS8Call.",
                {"is_response": is_response},
            )
        ],
    )
    if trace_id is not None:
        message["_js8link_diagnostic_trace_id"] = trace_id

    # The API client can receive events while background tasks are writing
    # monitor data. Serialize this high-volume diagnostic table and allow a
    # longer retry window than SQLite's default busy timeout.
    async with api_message_write_lock:
        for attempt in range(5):
            try:
                async with SessionLocal() as session:
                    entry = JS8APIMessage(
                        direction="rx",
                        message_type=message.get("type", ""),
                        request_id=params.get("_ID") if params.get("_ID") != -1 else None,
                        params_json=str(params),
                        value_json=str(message.get("value", "")),
                        utc_timestamp=utc_naive(event_timestamp(message)),
                        raw_payload=str(
                            {
                                key: item
                                for key, item in message.items()
                                if key != "_js8link_diagnostic_trace_id"
                            }
                        ),
                    )
                    session.add(entry)
                    await session.commit()
                await _append_diagnostic_processing(
                    trace_id,
                    "Raw API message stored",
                    "The raw JS8Call API envelope was stored in the diagnostic history.",
                    payload={"message_type": message_type},
                )
                # RX.BAND_ACTIVITY is normally returned as the response to
                # RX.GET_BAND_ACTIVITY rather than delivered as an async
                # event. Route that response through the same monitor parser
                # so the diagnostic timeline shows the actual data handling.
                if is_response and message_type == "RX.BAND_ACTIVITY":
                    if rx_enabled:
                        try:
                            await _handle_activity(
                                message,
                                message_type,
                                params,
                                str(message.get("value") or ""),
                            )
                            await _append_diagnostic_processing(
                                trace_id,
                                "Monitor traffic persisted",
                                "The band-activity snapshot was expanded, filtered for stale entries, "
                                "deduplicated and stored for the Band Monitor.",
                            )
                        except Exception as error:
                            await _append_diagnostic_processing(
                                trace_id,
                                "Monitor traffic processing failed",
                                "The band-activity snapshot was received but could not be processed.",
                                outcome="failed",
                                payload={"error": str(error)},
                            )
                            raise
                    else:
                        await _append_diagnostic_processing(
                            trace_id,
                            "RX processing skipped",
                            "The band-activity snapshot was received, but application RX processing is disabled.",
                            outcome="skipped",
                        )
                return
            except sa_exc.OperationalError as error:
                if "locked" not in str(error).lower() or attempt == 4:
                    logger.warning("Could not persist JS8Call API message after database lock: %s", error)
                    await _append_diagnostic_processing(
                        trace_id,
                        "Raw API message storage",
                        "The API envelope could not be stored because the database remained locked.",
                        outcome="failed",
                        payload={"error": str(error)},
                    )
                    return
                await asyncio.sleep(0.25 * (2**attempt))
            except Exception:
                logger.exception("Failed to persist JS8Call API message")
                await _append_diagnostic_processing(
                    trace_id,
                    "Raw API message storage",
                    "The API envelope could not be stored.",
                    outcome="failed",
                )
                return


async def on_js8_api_malformed(raw_message: bytes) -> None:
    """Keep malformed JS8Call input visible in diagnostics instead of dropping it."""
    await _record_diagnostic_trace(
        source="js8_api",
        event_type="INVALID_JSON",
        summary="Malformed JS8Call input received",
        interpretation="JS8Call sent data that was not valid JSON and could not be processed.",
        raw_payload={"raw_text": raw_message.decode("utf-8", errors="replace")},
        severity="error",
        processing=[
            (
                "JSON parsing",
                "failed",
                "The incoming JS8Call line was retained for diagnosis but could not be decoded.",
                None,
            )
        ],
    )


async def on_js8_api_outbound(message: dict[str, Any], expects_response: bool) -> None:
    """Record commands JS8Link sends to JS8Call, including automated work."""
    message_type = str(message.get("type") or "UNKNOWN").upper()
    meaning = describe_api_message(message, outbound=True)
    await _record_diagnostic_trace(
        source="automatic_task" if message_type.startswith("STATION.GET_") else "js8_api",
        event_type=message_type,
        summary=meaning.summary,
        interpretation=(
            meaning.interpretation
            + (" JS8Link is waiting for the correlated response." if expects_response else "")
        ),
        raw_payload=message,
        processing=[
            ("JS8Call API output", "sent", "The JSON command was written to the JS8Call TCP connection.", None)
        ],
    )


# ---------------------------------------------------------------------------
# record_heartbeat
# ---------------------------------------------------------------------------
async def record_heartbeat(js8_client: JS8CallClient) -> None:
    """Transmit a local HEARTBEAT directed command if conditions are met."""
    if not local_callsign or not tx_enabled:
        return
    async with SessionLocal() as session:
        last_entry = await session.scalar(
            select(ReceivedMessage)
            .where(
                ReceivedMessage.is_heartbeat.is_(True),
                ReceivedMessage.from_callsign == local_callsign,
            )
            .order_by(desc(ReceivedMessage.received_at))
        )
        if last_entry and last_entry.received_at:
            elapsed = utcnow() - last_entry.received_at
            if elapsed < _HEARTBEAT_INTERVAL:
                return
    try:
        tx_state["pending_heartbeat_beacon"] = {
            "text": f"{local_callsign or 'TX'} @HB HEARTBEAT",
            "queued_at": utcnow(),
        }
        await js8_client.send("STATION.SEND_HB")
    except Exception:
        logger.exception("Heartbeat grid request failed")


# ---------------------------------------------------------------------------
# get_config
# ---------------------------------------------------------------------------
async def _get_app_config(session: AsyncSession) -> AppConfig:
    result = await session.scalars(select(AppConfig).where(AppConfig.id == 1))
    config = result.one_or_none()
    if config is None:
        config = AppConfig(id=1)
        session.add(config)
        await session.commit()
        await session.refresh(config)
    return config


# ---------------------------------------------------------------------------
# connect_client
# ---------------------------------------------------------------------------
async def connect_client(host: str, port: int, js8_client: JS8CallClient) -> dict[str, Any]:
    global local_callsign
    await js8_client.connect()
    info = await js8_client.request("STATION.GET_CALLSIGN")
    callsign = _station_response_text(info, "CALLSIGN")
    if callsign:
        local_callsign = callsign.strip().upper()
        grid = await _station_text(js8_client, "STATION.GET_GRID")
        async with SessionLocal() as session:
            await _ensure_local_station(session, local_callsign, grid)
            await session.commit()
    return info


# ---------------------------------------------------------------------------
# connection_monitor
# ---------------------------------------------------------------------------
async def connection_monitor() -> None:
    """Reconnect to JS8Call if the connection drops."""
    retry_delay = 5.0
    while True:
        await asyncio.sleep(retry_delay)
        if client is None:
            retry_delay = 5.0
            continue
        if not client.connected:
            host, port = client.host, client.port
            try:
                async with SessionLocal() as session:
                    config = await _get_app_config(session)
                    host, port = config.js8_host, config.js8_port
                await client.connect()
                await broadcast(
                    event="connection.reconnected",
                    data={"host": host, "port": port},
                )
                retry_delay = 5.0
            except (ConnectionRefusedError, TimeoutError, OSError) as error:
                logger.warning(
                    "JS8Call is unavailable at %s:%s; retrying in %.0f seconds (%s)",
                    host,
                    port,
                    min(retry_delay * 2, 300),
                    error,
                )
                retry_delay = min(retry_delay * 2, 300)
            except Exception:
                logger.exception("Unexpected error while reconnecting to JS8Call")
                retry_delay = min(retry_delay * 2, 300)


# ---------------------------------------------------------------------------
# offset_optimizer
# ---------------------------------------------------------------------------
async def offset_optimizer() -> None:
    """Periodically recommend the best TX offset."""
    while True:
        await asyncio.sleep(30)
        if not client or not client.connected or not local_callsign:
            continue
        try:
            async with SessionLocal() as session:
                config = await _get_app_config(session)
                if config.offset_mode != "auto":
                    continue
                context = await _radio_context(client)
                dial = context.get("dial")
                speed = context.get("speed")
                band = band_from_frequency(dial)
                mode_val = mode_from_speed(speed)
                current_offset = context.get("offset")

                # Get free offsets from JS8Call
                free_segments = []
                try:
                    free_info = await client.request("RX.GET_FREE_OFFSETS", params={"SPEED": speed})
                    free_segments = (free_info.get("params") or {}).get("FREE", [])
                except Exception:
                    pass  # Fall back to best_offset only

                # Pick best offset considering both DB history and real-time free segments
                rec = await best_offset(
                    session,
                    band=band,
                    window_minutes=15,
                    current_offset=current_offset,
                    speed=speed,
                )
                chosen_offset = rec.offset

                if free_segments and chosen_offset is not None:
                    # Check if chosen_offset falls within any free segment
                    in_free = any(seg.get("LOW", 0) <= chosen_offset <= seg.get("HIGH", 9999) for seg in free_segments)
                    if not in_free:
                        # Pick the widest free segment's center
                        widest = max(free_segments, key=lambda s: s.get("WIDTH", 0))
                        chosen_offset = (widest.get("LOW", 1000) + widest.get("HIGH", 2000)) // 2

                if chosen_offset is not None and chosen_offset != current_offset:
                    await client.send(
                        "RIG.SET_FREQ",
                        params={"DIAL": dial, "OFFSET": chosen_offset},
                    )
                    logger.info(
                        "Auto-offset changed to %s Hz (band=%s, mode=%s)",
                        chosen_offset,
                        band,
                        mode_val,
                    )
        except Exception:
            logger.exception("Offset optimizer failed")


# ---------------------------------------------------------------------------
# cleanup_received_messages
# ---------------------------------------------------------------------------
async def _cleanup_retained_messages(session: AsyncSession, config: AppConfig) -> None:
    """Apply the received-traffic and JS8Call API diagnostic retention policies."""
    now = utcnow()
    received_cutoff = now - timedelta(days=max(config.received_message_retention_days, 1))
    api_cutoff = now - timedelta(days=max(config.api_message_retention_days, 1))
    diagnostic_cutoff = now - timedelta(days=max(config.diagnostics_retention_days, 1))
    query_cutoff = now - timedelta(days=30)
    band_activity_cutoff = now - timedelta(hours=24)

    await session.execute(delete(ReceivedMessage).where(ReceivedMessage.received_at < received_cutoff))
    await session.execute(delete(TransmittedMessage).where(TransmittedMessage.transmitted_at < received_cutoff))
    await session.execute(delete(ArqReceipt).where(ArqReceipt.first_received_at < received_cutoff))
    await session.execute(delete(StationQuery).where(StationQuery.requested_at < query_cutoff))
    await session.execute(delete(ActivityEvent).where(ActivityEvent.created_at < api_cutoff))
    await session.execute(
        delete(JS8APIMessage).where(
            or_(
                JS8APIMessage.received_at < api_cutoff,
                and_(
                    JS8APIMessage.message_type == "RX.BAND_ACTIVITY",
                    JS8APIMessage.received_at < band_activity_cutoff,
                ),
            )
        )
    )
    await session.execute(delete(DiagnosticProcessing).where(DiagnosticProcessing.created_at < diagnostic_cutoff))
    await session.execute(delete(DiagnosticTrace).where(DiagnosticTrace.created_at < diagnostic_cutoff))
    await session.commit()


async def cleanup_received_messages() -> None:
    """Periodically remove received traffic and JS8Call API diagnostics."""
    while True:
        try:
            async with SessionLocal() as session:
                config = await _get_app_config(session)
                await _cleanup_retained_messages(session, config)
        except Exception:
            logger.exception("Retention cleanup failed")
        await asyncio.sleep(3600)  # hourly


# ---------------------------------------------------------------------------
# arq_retry_scheduler
# ---------------------------------------------------------------------------
async def arq_retry_scheduler() -> None:
    poll_interval = 1.0
    max_poll = 30.0
    while True:
        try:
            current_time = now()
            had_work = False
            async with SessionLocal() as session:
                expired = (
                    await session.scalars(
                        select(TransmittedMessage)
                        .where(
                            TransmittedMessage.delivery_mode == "confirmed",
                            TransmittedMessage.delivery_status.in_(("awaiting_ack", "retrying")),
                            TransmittedMessage.ack_deadline.is_not(None),
                            TransmittedMessage.ack_deadline <= current_time,
                        )
                        .order_by(TransmittedMessage.ack_deadline)
                        .limit(10)
                    )
                ).all()
                for delivery in expired:
                    had_work = True
                    if delivery.attempts >= delivery.max_attempts:
                        delivery.status = "failed"
                        delivery.delivery_status = "failed"
                        delivery.last_error = "No acknowledgement received"
                        delivery.ack_deadline = None
                        await broadcast(
                            event="chat.delivery.updated",
                            data={
                                "callsign": delivery.callsign,
                                "protocol_id": delivery.protocol_id,
                                "status": "failed",
                            },
                        )
                        continue
                    if not client or not client.connected or not delivery.callsign or not delivery.protocol_id:
                        delivery.ack_deadline = current_time + timedelta(seconds=15)
                        # Still count disconnected cycles toward max_attempts so the
                        # message eventually fails instead of looping forever.
                        delivery.attempts = (delivery.attempts or 0) + 1
                        if (delivery.attempts or 0) >= (delivery.max_attempts or 3):
                            delivery.status = "failed"
                            delivery.delivery_status = "failed"
                            delivery.last_error = "Could not reach JS8Call for delivery"
                            delivery.ack_deadline = None
                            await broadcast(
                                event="chat.delivery.updated",
                                data={
                                    "callsign": delivery.callsign,
                                    "protocol_id": delivery.protocol_id,
                                    "status": "failed",
                                },
                            )
                        continue
                    delivery.status = "retrying"
                    delivery.delivery_status = "retrying"
                    await session.commit()
                    await broadcast(
                        event="chat.delivery.updated",
                        data={
                            "callsign": delivery.callsign,
                            "protocol_id": delivery.protocol_id,
                            "status": "retrying",
                        },
                    )
                    try:
                        wire_text = encode_data(delivery.text, delivery.protocol_id)
                        await transmit_js8_text(
                            client,
                            f"{delivery.callsign} {wire_text}",
                            peer=delivery.callsign,
                        )
                        await session.refresh(delivery)
                        if delivery.delivery_status == "delivered":
                            continue
                        delivery.attempts += 1
                        delivery.status = "awaiting_ack"
                        delivery.delivery_status = "awaiting_ack"
                        delivery.ack_deadline = now() + timedelta(
                            seconds=ack_timeout_seconds(delivery.mode)
                        )
                        delivery.last_error = None
                    except Exception as error:
                        delivery.last_error = str(error)
                        delivery.ack_deadline = now() + timedelta(seconds=15)
                await session.commit()
            poll_interval = 1.0 if had_work else min(poll_interval * 1.5, max_poll)
            await asyncio.sleep(poll_interval)
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(poll_interval)


# ---------------------------------------------------------------------------
# Utility: upsert station from event
# ---------------------------------------------------------------------------
async def _upsert_station(
    session: AsyncSession,
    callsign: str,
    *,
    snr: int | None = None,
    frequency: object = None,
    offset: object = None,
    mode: str | None = None,
    tdrift: float | None = None,
    observed_at: datetime | None = None,
) -> Station | None:
    if not callsign:
        return None
    result = await session.scalars(select(Station).where(Station.callsign == callsign))
    station = result.one_or_none()
    now_ts = utc_naive(observed_at) or now()
    is_new = station is None
    if station is None:
        location = callsign_location(callsign)
        station = Station(
            callsign=callsign,
            grid=None,
            latitude=location.latitude if location else None,
            longitude=location.longitude if location else None,
            country=location.country if location else None,
            location_source="prefix" if location else None,
            first_seen=now_ts,
            last_seen=now_ts,
            last_snr=snr,
            message_count=1,
        )
        session.add(station)
        await session.flush()  # ensure .id is populated before any caller uses it as FK
    else:
        if station.last_seen is None or now_ts > station.last_seen:
            station.last_seen = now_ts
    if snr is not None:
        station.last_snr = snr
    if mode is not None:
        station.last_mode = mode
    if offset is not None:
        try:
            station.last_offset = int(offset)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            pass
    if tdrift is not None:
        station.last_tdrift = tdrift
    if not is_new:
        station.message_count = (station.message_count or 0) + 1
    return station


async def _ensure_local_station(
    session: AsyncSession,
    callsign: str,
    grid: str | None,
) -> Station:
    """Ensure the local station exists after a purge or fresh installation."""
    normalized = callsign.strip().upper()
    station = await session.scalar(select(Station).where(Station.callsign == normalized))
    normalized_grid = grid.strip().upper() if grid else None
    coordinates = try_grid_to_coordinates(normalized_grid)
    if station is None:
        station = Station(
            callsign=normalized,
            grid=normalized_grid,
            latitude=coordinates[0] if coordinates else None,
            longitude=coordinates[1] if coordinates else None,
            location_source="grid" if coordinates else None,
            first_seen=now(),
            last_seen=now(),
            message_count=0,
        )
        session.add(station)
    elif normalized_grid:
        station.grid = normalized_grid
        if coordinates:
            station.latitude, station.longitude = coordinates
            station.location_source = "grid"
    return station


async def _upsert_station_from_event(
    session: AsyncSession,
    callsign: str,
    *,
    snr: int | None = None,
    frequency: object = None,
    offset: object = None,
    mode: str | None = None,
    tdrift: float | None = None,
    observed_at: datetime | None = None,
) -> Station | None:
    return await _upsert_station(
        session,
        callsign,
        snr=snr,
        frequency=frequency,
        offset=offset,
        mode=mode,
        tdrift=tdrift,
        observed_at=observed_at,
    )


async def _update_station_link(
    session: AsyncSession,
    source_station_id: int,
    target_station_id: int,
    *,
    relation_type: str = "heartbeat",
    snr: int | None = None,
    band: str | None = None,
) -> None:
    result = await session.scalars(
        select(StationLink).where(
            StationLink.source_station_id == source_station_id,
            StationLink.target_station_id == target_station_id,
            StationLink.relation_type == relation_type,
        )
    )
    link = result.one_or_none()
    now_ts = now()
    if link is None:
        link = StationLink(
            source_station_id=source_station_id,
            target_station_id=target_station_id,
            relation_type=relation_type,
            band=band,
            latest_snr=snr,
            average_snr=float(snr) if snr is not None else None,
            best_snr=snr,
            observation_count=1,
            first_seen=now_ts,
            last_seen=now_ts,
        )
        session.add(link)
    else:
        link.last_seen = now_ts
        link.observation_count += 1
        if snr is not None:
            link.latest_snr = snr
            if link.best_snr is None or snr > link.best_snr:
                link.best_snr = snr
            if link.average_snr is not None:
                link.average_snr = (link.average_snr * (link.observation_count - 1) + snr) / link.observation_count
            else:
                link.average_snr = float(snr)
        if band is not None:
            link.band = band


# ===========================================================================
# API Endpoints
# ===========================================================================


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/api/health", response_model=HealthResponse)
async def api_health() -> dict[str, Any]:
    return {
        "status": "ok",
        "connected": client is not None and client.connected if client else False,
        "callsign": local_callsign,
        "version": __version__,
    }


@app.get("/api/about", response_model=AboutResponse)
async def api_about(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Expose release and connection metadata without secrets or local paths."""
    config = await _get_app_config(session)
    return {
        "application": "JS8Link",
        "version": __version__,
        "channel": "alpha",
        "license": "GNU General Public License v3.0 (GPL-3.0-only)",
        "repository_url": "https://github.com/erikdewildt/JS8Link",
        "releases_url": "https://github.com/erikdewildt/JS8Link/releases",
        "platform": platform.system(),
        "architecture": platform.machine(),
        "js8call_protocol": "tcp",
        "js8call_host": config.js8_host,
        "js8call_port": config.js8_port,
        "js8call_connected": bool(client and client.connected),
        "update_state": "unknown",
    }


@app.get("/api/changelog")
async def api_changelog() -> dict[str, Any]:
    changelog_path = PROJECT_ROOT / "CHANGELOG.md"
    if not changelog_path.exists():
        raise HTTPException(status_code=404, detail="Changelog not found")
    return {"version": __version__, "releases": load_changelog(changelog_path)}


@app.get("/api/help", response_model=HelpCatalogResponse)
async def api_help(language: str = Query(default="en", alias="lang", max_length=8)) -> dict[str, Any]:
    """Return the localised, bundled help catalog without requiring the database."""
    try:
        return load_catalog(language)
    except (OSError, json.JSONDecodeError) as exc:
        logger.exception("Failed to load help catalog")
        raise HTTPException(status_code=500, detail="Help content is unavailable") from exc


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
@app.post("/api/auth")
async def api_auth(
    body: AuthRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    valid = await _verify_password(session, body.password)
    if not valid:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"authenticated": True}


@app.post("/api/auth/login")
async def api_auth_login(
    body: AuthRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Compatibility endpoint used by the web application's login form."""
    return await api_auth(body, session)


@app.post("/api/auth/logout")
async def api_auth_logout() -> dict[str, bool]:
    return {"authenticated": False}


@app.get("/api/auth/logout")
async def api_auth_logout_get_not_allowed() -> None:
    raise HTTPException(status_code=405, detail="Method Not Allowed")


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
@app.get("/api/setup/status", response_model=SetupStatusResponse)
async def api_setup_status(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    config = await _get_app_config(session)
    auth = await _get_auth_config(session)
    return {
        "setup_complete": config.setup_complete,
        "host": config.js8_host,
        "port": config.js8_port,
        "connected": bool(client and client.connected),
        "auth_enabled": auth.enabled,
    }


@app.post("/api/setup/test-connection")
async def api_setup_test_connection(body: ConnectionRequest) -> dict[str, Any]:
    probe = JS8CallClient(
        host=body.host,
        port=body.port,
        on_message=on_js8_api_message,
        on_outbound=on_js8_api_outbound,
        on_malformed=on_js8_api_malformed,
    )
    try:
        await probe.connect()
        return {"connected": True, "version": probe.version or "unknown"}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to connect to JS8Call: {exc}") from exc
    finally:
        await probe.close()


@app.post("/api/setup")
@app.post("/api/setup/complete")
async def api_setup(
    body: SetupRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    global client, local_callsign

    config = await _get_app_config(session)
    config.js8_host = body.host
    config.js8_port = body.port
    config.setup_complete = True

    auth = await _get_auth_config(session)
    auth.enabled = body.auth_enabled
    if body.auth_enabled and body.username and body.password:
        auth.username = body.username
        auth.password_hash = ph.hash(body.password)

    await session.commit()

    # Connect immediately
    if client:
        await client.close()
    client = JS8CallClient(
        host=body.host,
        port=body.port,
        on_event=on_js8_event,
        on_message=on_js8_api_message,
        on_outbound=on_js8_api_outbound,
        on_malformed=on_js8_api_malformed,
    )
    try:
        await connect_client(body.host, body.port, client)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to connect to JS8Call: {exc}") from exc

    return {"status": "ok", "callsign": local_callsign}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
@app.get("/api/config", response_model=ConfigResponse)
async def api_get_config(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    config = await _get_app_config(session)
    auth = await _get_auth_config(session)
    try:
        update_repository = origin_github_repository(PROJECT_ROOT)
    except UpdateError:
        update_repository = None
    return {
        "host": config.js8_host,
        "port": config.js8_port,
        "auth_enabled": auth.enabled,
        "setup_complete": config.setup_complete,
        "offset_mode": config.offset_mode,
        "fixed_offset": config.fixed_offset,
        "heartbeat_offset_mode": config.heartbeat_offset_mode,
        "fixed_heartbeat_offset": config.fixed_heartbeat_offset,
        "received_message_retention_days": config.received_message_retention_days,
        "api_message_retention_days": config.api_message_retention_days,
        "diagnostics_enabled": config.diagnostics_enabled,
        "diagnostics_retention_days": config.diagnostics_retention_days,
        "update_repository": update_repository,
        "update_branch": config.update_branch,
        "station_queries_enabled": config.station_queries_enabled,
        "query_interval_snr_minutes": config.query_interval_snr_minutes,
        "query_interval_hearing_minutes": config.query_interval_hearing_minutes,
        "query_interval_info_days": config.query_interval_info_days,
        "query_interval_grid_days": config.query_interval_grid_days,
        "query_interval_status_hours": config.query_interval_status_hours,
        "query_max_per_hour": config.query_max_per_hour,
        "query_cooldown_seconds": config.query_cooldown_seconds,
        "query_timeout_minutes": config.query_timeout_minutes,
        "band_scope_minutes": config.band_scope_minutes,
        "toast_duration_seconds": config.toast_duration_seconds,
    }


@app.patch("/api/config")
async def api_patch_config(
    body: ConfigPatch,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    global client, local_callsign

    config = await _get_app_config(session)
    if body.host is not None:
        config.js8_host = body.host
    if body.port is not None:
        config.js8_port = body.port
    if body.update_repository is not None:
        try:
            config.update_repository = normalize_github_repository(body.update_repository)
        except UpdateError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    if body.update_branch is not None:
        try:
            config.update_branch = validate_branch(body.update_branch)
        except UpdateError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    if body.station_queries_enabled is not None:
        config.station_queries_enabled = body.station_queries_enabled
    for field_name in (
        "query_interval_snr_minutes",
        "query_interval_hearing_minutes",
        "query_interval_info_days",
        "query_interval_grid_days",
        "query_interval_status_hours",
        "query_max_per_hour",
        "query_cooldown_seconds",
        "query_timeout_minutes",
        "toast_duration_seconds",
        "api_message_retention_days",
        "diagnostics_retention_days",
    ):
        value = getattr(body, field_name)
        if value is not None:
            setattr(config, field_name, value)
    if body.diagnostics_enabled is not None:
        config.diagnostics_enabled = body.diagnostics_enabled

    auth = await _get_auth_config(session)
    if body.auth_enabled is not None:
        auth.enabled = body.auth_enabled
    if body.username is not None:
        auth.username = body.username
    if body.password is not None:
        auth.password_hash = ph.hash(body.password)

    await session.commit()

    # Reconnect if host/port changed
    if body.host is not None or body.port is not None:
        if client:
            await client.close()
        client = JS8CallClient(
            host=config.js8_host,
            port=config.js8_port,
            on_event=on_js8_event,
            on_message=on_js8_api_message,
            on_outbound=on_js8_api_outbound,
            on_malformed=on_js8_api_malformed,
        )
        try:
            await connect_client(config.js8_host, config.js8_port, client)
        except Exception as exc:
            logger.warning("Reconnection after config change failed: %s", exc)

    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Application updates
# ---------------------------------------------------------------------------
async def _run_update_command(command: list[str], cwd: Path) -> str:
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await process.communicate()
    result = stdout.decode(errors="replace").strip()
    if process.returncode != 0:
        tail = "\n".join(result.splitlines()[-12:])
        raise UpdateError(f"Command failed ({command[0]}): {tail or 'unknown error'}")
    return result


async def _restart_systemd_service() -> None:
    await asyncio.sleep(2)
    try:
        await _run_update_command(["systemctl", "--user", "restart", "js8link.service"], PROJECT_ROOT)
    except UpdateError:
        logger.exception("The update succeeded, but the SystemD service could not be restarted")


def _configured_update(config: AppConfig) -> tuple[str, str]:
    try:
        return origin_github_repository(PROJECT_ROOT), validate_branch(config.update_branch)
    except UpdateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get("/api/update/check")
async def api_check_update(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    config = await _get_app_config(session)
    # Release checks must also work from a packaged executable, where there is
    # deliberately no Git checkout. Prefer the configured repository, then use
    # the canonical public project as a safe fallback.
    try:
        repository = normalize_github_repository(config.update_repository or "erikdewildt/JS8Link")
    except UpdateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    try:
        releases = await asyncio.to_thread(get_github_releases, repository)
    except UpdateError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    current_version = parse_version(__version__)
    latest = releases[0] if releases else None
    artifact_names = platform_artifact_names()
    matching_asset = next((asset for asset in (latest.assets if latest else ()) if asset in artifact_names), None)
    reason = None if matching_asset else "No packaged update is available for this platform"

    return {
        "repository": repository,
        "branch": "releases",
        "current_commit": f"v{current_version}",
        "latest_commit": latest.tag if latest else f"v{current_version}",
        "latest_message": latest.name if latest else "No public release found",
        "latest_url": latest.url if latest else f"https://github.com/{repository}/releases",
        "latest_version": latest.version if latest else None,
        "latest_prerelease": latest.prerelease if latest else None,
        "platform_artifact": matching_asset,
        "update_available": latest is not None and parse_version(latest.version) > current_version,
        "can_update": False,
        "reason": reason
        or (
            "Download the release manually; automatic executable replacement is disabled "
            "in alpha releases."
        ),
    }


@app.post("/api/update/apply")
async def api_apply_update(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    raise HTTPException(
        status_code=409,
        detail=(
            "Automatic executable replacement is disabled for JS8Link alpha releases; "
            "download the GitHub release manually."
        ),
    )

    # Kept below for source-checkout compatibility during the transition to
    # release-based updates. The packaged alpha never reaches this path.
    if update_lock.locked():
        raise HTTPException(status_code=409, detail="An update is already running")

    config = await _get_app_config(session)
    repository, branch = _configured_update(config)
    async with update_lock:
        try:
            remote = await asyncio.to_thread(get_github_branch, repository, branch)
            current_commit = current_git_commit(PROJECT_ROOT)
            if current_commit is None:
                raise UpdateError("This installation is not a Git checkout")
            if tracked_changes(PROJECT_ROOT):
                raise UpdateError("The installation contains local source changes")
            if current_commit == remote.commit:
                return {"status": "current", "commit": current_commit, "restart_scheduled": False}

            git = shutil.which("git")
            uv = shutil.which("uv")
            npm = shutil.which("npm")
            if not git or not uv or not npm:
                raise UpdateError("git, uv and npm must be available to install an update")

            await _run_update_command(
                [git, "fetch", "--no-tags", "origin", branch],
                PROJECT_ROOT,
            )
            fetched_commit = git_output(PROJECT_ROOT, "rev-parse", "FETCH_HEAD")
            if fetched_commit != remote.commit:
                raise UpdateError("The downloaded commit does not match the GitHub update check")

            frontend_dist = PROJECT_ROOT / "frontend" / "dist"
            frontend_backup = settings.data_dir / ".frontend-update-backup"
            if frontend_backup.exists():
                await asyncio.to_thread(shutil.rmtree, frontend_backup)
            if frontend_dist.exists():
                await asyncio.to_thread(shutil.copytree, frontend_dist, frontend_backup)

            try:
                await _run_update_command([git, "merge", "--ff-only", remote.commit], PROJECT_ROOT)
                await _run_update_command([uv, "sync", "--frozen"], PROJECT_ROOT / "backend")
                await _run_update_command([npm, "ci"], PROJECT_ROOT / "frontend")
                await _run_update_command([npm, "run", "build"], PROJECT_ROOT / "frontend")
                await _run_update_command([uv, "run", "alembic", "upgrade", "head"], PROJECT_ROOT / "backend")
            except UpdateError:
                await _run_update_command([git, "reset", "--hard", current_commit], PROJECT_ROOT)
                try:
                    await _run_update_command([uv, "sync", "--frozen"], PROJECT_ROOT / "backend")
                except UpdateError:
                    logger.exception("Could not restore the previous backend dependencies")
                if frontend_backup.exists():
                    if frontend_dist.exists():
                        await asyncio.to_thread(shutil.rmtree, frontend_dist)
                    await asyncio.to_thread(shutil.copytree, frontend_backup, frontend_dist)
                raise
            finally:
                if frontend_backup.exists():
                    await asyncio.to_thread(shutil.rmtree, frontend_backup)

            restart_scheduled = bool(os.name != "nt" and os.environ.get("INVOCATION_ID") and shutil.which("systemctl"))
            if restart_scheduled:
                asyncio.create_task(_restart_systemd_service())
            return {
                "status": "updated",
                "previous_commit": current_commit,
                "commit": remote.commit,
                "restart_scheduled": restart_scheduled,
                "restart_required": not restart_scheduled,
            }
        except UpdateError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error


# ---------------------------------------------------------------------------
# Radio context helpers
# ---------------------------------------------------------------------------
async def _radio_context(js8_client: JS8CallClient) -> dict[str, Any]:
    """Fetch the current radio state (dial, offset, speed) from JS8Call.

    ``STATION.GET_STATUS`` only returns the station status text — the dial
    frequency, offset and speed live in ``RIG.GET_FREQ`` and ``MODE.GET_SPEED``.
    Each call is best-effort; missing values are simply omitted.
    """
    context: dict[str, Any] = {}
    try:
        freq_info = await js8_client.request("RIG.GET_FREQ")
        context["dial"] = _response_param(freq_info, "DIAL")
        context["offset"] = _response_param(freq_info, "OFFSET")
    except Exception:
        pass
    try:
        speed_info = await js8_client.request("MODE.GET_SPEED")
        context["speed"] = _response_param(speed_info, "SPEED")
    except Exception:
        pass
    return context


def _response_param(response: dict[str, Any], *names: str) -> Any:
    """Read a JS8Call response parameter without relying on key casing/layout."""
    params = response.get("params") or {}
    for name in names:
        for key, value in params.items():
            if str(key).upper() == name.upper():
                return value
        for key, value in response.items():
            if str(key).upper() == name.upper():
                return value
    return None


def _station_response_text(response: dict[str, Any], field: str) -> str | None:
    """Read station text from both JS8Call response layouts.

    JS8Call-improved versions have returned station values either in the
    response ``value`` field or in a named ``params`` field.  Accept both so
    status and callsign discovery does not depend on the exact minor version.
    """
    value = response.get("value")
    if value is not None and str(value).strip():
        return str(value).strip()
    params = response.get("params") or {}
    for name in (field, "value"):
        for key, value in params.items():
            if str(key).upper() == name.upper() and value is not None and str(value).strip():
                return str(value).strip()
    return None


async def _station_text(js8_client: JS8CallClient, command: str) -> str | None:
    """Best-effort helper for JS8Call station text responses."""
    try:
        info = await js8_client.request(command)
        field = command.rsplit(".", maxsplit=1)[-1].removeprefix("GET_")
        return _station_response_text(info, field)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
@app.get("/api/status", response_model=StatusResponse)
async def api_status(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    config = await _get_app_config(session)
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        context = await _radio_context(client)
        dial = context.get("dial")
        speed = context.get("speed")
        offset = context.get("offset")

        tx_queue_depth = None
        try:
            queue_info = await client.request("TX.GET_QUEUE_DEPTH")
            tx_queue_depth = (queue_info.get("params") or {}).get("DEPTH")
        except Exception:
            pass

        os_name = None
        os_kernel = None
        os_kernel_version = None
        try:
            os_info = await client.request("STATION.GET_OS")
            os_name = _response_param(os_info, "OS_NAME")
            os_kernel = _response_param(os_info, "OS_KERNEL")
            os_kernel_version = _response_param(os_info, "OS_KERNEL_VERSION")
        except Exception:
            pass

        grid = await _station_text(client, "STATION.GET_GRID")
        info = await _station_text(client, "STATION.GET_INFO")
        status_text = await _station_text(client, "STATION.GET_STATUS")

        return {
            "connected": True,
            "callsign": local_callsign,
            "station": {"value": local_callsign},
            "frequency": {"params": {"DIAL": dial, "OFFSET": offset}},
            "mode": {"params": {"SPEED": speed}},
            "queue": {"params": {}},
            "dial": dial,
            "offset": offset,
            "band": band_from_frequency(dial),
            "speed": speed,
            "mode_name": mode_from_speed(speed),
            "grid": grid,
            "info": info,
            "status_text": status_text,
            "version": client.version,
            "js8call_version": client.version,
            "offset_mode": config.offset_mode,
            "fixed_offset": config.fixed_offset,
            "normal_offset": offset or config.fixed_offset,
            "tx_queue_depth": tx_queue_depth,
            "rx_enabled": rx_enabled,
            "tx_enabled": tx_enabled,
            "os_name": os_name,
            "os_kernel": os_kernel,
            "os_kernel_version": os_kernel_version,
        }
    except Exception:
        return {
            "connected": False,
            "callsign": local_callsign,
            "station": {"value": local_callsign},
            "frequency": {"params": {}},
            "mode": {"params": {}},
            "queue": {"params": {}},
            "offset_mode": config.offset_mode,
            "fixed_offset": config.fixed_offset,
            "normal_offset": config.fixed_offset,
            "js8call_version": config.js8call_version,
            "rx_enabled": rx_enabled,
            "tx_enabled": tx_enabled,
        }


# ---------------------------------------------------------------------------
# JS8 Settings
# ---------------------------------------------------------------------------
@app.get("/api/js8/settings")
async def api_get_js8_settings() -> dict[str, Any]:
    global local_callsign
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        context = await _radio_context(client)
        dial = context.get("dial")
        speed = context.get("speed")
        offset = context.get("offset")

        callsign = local_callsign or await _station_text(client, "STATION.GET_CALLSIGN")
        if callsign:
            local_callsign = callsign.strip().upper()
        grid = await _station_text(client, "STATION.GET_GRID") or ""
        info = await _station_text(client, "STATION.GET_INFO") or ""
        status = await _station_text(client, "STATION.GET_STATUS") or ""

        config_fields = {}
        try:
            config_info = await client.request("STATION.GET_CONFIG")
            cfg = config_info.get("params") or {}
            config_fields = {
                "auto_reply": cfg.get("AUTO_REPLY"),
                "js8hb": cfg.get("JS8HB"),
                "hback": cfg.get("HBACK"),
                "multi_decoder": cfg.get("MULTI_DECODER"),
                "hb_interval": cfg.get("HB_INTERVAL"),
                "monitor": cfg.get("MONITOR"),
                "tx_enabled": cfg.get("TX_ENABLED"),
                "groups": cfg.get("GROUPS"),
                "avoid_allcall": cfg.get("AVOID_ALLCALL"),
            }
        except Exception:
            pass

        spot_enabled = None
        try:
            spot_info = await client.request("STATION.GET_SPOT")
            spot_value = _response_param(spot_info, "value", "SPOT", "ENABLED")
            if isinstance(spot_value, str):
                spot_enabled = spot_value.strip().lower() in {"1", "true", "yes", "on"}
            else:
                spot_enabled = bool(spot_value)
        except Exception:
            pass

        return {
            "callsign": local_callsign or "",
            "grid": grid,
            "info": info,
            "status": status,
            "dial": dial,
            "offset": offset,
            "speed": speed,
            "mode": mode_from_speed(speed),
            "band": band_from_frequency(dial),
            "spot_enabled": spot_enabled,
            "spot": spot_enabled,
            **config_fields,
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.patch("/api/js8/settings")
async def api_patch_js8_settings(
    body: JS8SettingsPatch,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        if body.grid is not None:
            await client.send("STATION.SET_GRID", value=body.grid)
        if body.info is not None:
            await client.send("STATION.SET_INFO", value=body.info)
        if body.status is not None:
            await client.send("STATION.SET_STATUS", value=body.status)
        if body.dial is not None:
            await client.send("RIG.SET_FREQ", params={"DIAL": body.dial, "OFFSET": body.offset or 1500})
        elif body.offset is not None:
            context = await _radio_context(client)
            current_dial = context.get("dial")
            if current_dial is not None:
                await client.send("RIG.SET_FREQ", params={"DIAL": current_dial, "OFFSET": body.offset})
        if body.speed is not None:
            await client.send("MODE.SET_SPEED", params={"SPEED": body.speed})
        if body.spot is not None:
            await client.send("STATION.SET_SPOT", value=str(body.spot).lower())

        config = await _get_app_config(session)
        if body.offset_mode is not None:
            config.offset_mode = body.offset_mode
        if body.fixed_offset is not None:
            config.fixed_offset = body.fixed_offset
        await session.commit()

        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Autoreply confirmation
# ---------------------------------------------------------------------------
@app.post("/api/js8/autoreply-confirm")
async def api_autoreply_confirm(body: AutoreplyConfirmRequest) -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        await client.send(
            "STATION.AUTOREPLY_CONFIRM_RESPONSE",
            params={"CONFIRM_ID": body.confirm_id, "ACCEPT": body.accept},
        )
        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# TX Halt (emergency stop)
# ---------------------------------------------------------------------------
@app.post("/api/js8/tx-halt")
async def api_tx_halt() -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        await client.send("RIG.TX_HALT")
        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Tune
# ---------------------------------------------------------------------------
@app.post("/api/js8/tune")
async def api_tune(body: TuneRequest) -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        await client.send("RIG.SET_TUNE", value=str(body.enabled).lower())
        return {"status": "ok", "tune": body.enabled}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Spot (PSK Reporter)
# ---------------------------------------------------------------------------
@app.post("/api/js8/spot")
async def api_set_spot(body: SpotRequest) -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        await client.send("STATION.SET_SPOT", value=str(body.enabled).lower())
        return {"status": "ok", "spot": body.enabled}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------
@app.get("/api/js8/groups")
async def api_get_groups() -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        config_info = await client.request("STATION.GET_CONFIG")
        groups = (config_info.get("params") or {}).get("GROUPS", [])
        return {"groups": groups if isinstance(groups, list) else []}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.put("/api/js8/groups")
async def api_set_groups(body: GroupsRequest) -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        await client.send("STATION.SET_GROUPS", params={"GROUPS": body.groups})
        return {"status": "ok", "groups": body.groups}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# PTT / Call Activity / OS / Station Settings
# ---------------------------------------------------------------------------
@app.get("/api/js8/ptt", response_model=PTTResponse)
async def api_get_ptt() -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        ptt_info = await client.request("RIG.GET_PTT")
        params = ptt_info.get("params") or {}
        return {
            "ptt": params.get("PTT", False),
            "message": params.get("MESSAGE", ""),
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/js8/rx-toggle")
async def api_rx_toggle(body: BoolToggleRequest) -> dict[str, Any]:
    """Toggle JS8Link RX processing.

    JS8Call-improved v3 exposes the MONITOR value for reading, but has no TCP
    setter for it.  The toggle therefore controls whether JS8Link processes
    incoming API events; the native JS8Call receiver remains unchanged.
    """
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    global rx_enabled
    rx_enabled = body.enabled
    return {
        "status": "ok",
        "rx_enabled": rx_enabled,
        "scope": "js8link",
        "message": "JS8Call has no API command to change MONITOR; local event processing was changed.",
    }


@app.post("/api/js8/tx-toggle")
async def api_tx_toggle(body: BoolToggleRequest) -> dict[str, Any]:
    """Toggle JS8Link TX and halt an active JS8Call transmission if needed.

    JS8Call-improved does not expose a persistent TX_ENABLED setter through the
    TCP API.  Disabling TX therefore blocks new JS8Link transmissions and uses
    the supported RIG.TX_HALT command to stop an active transmission.
    """
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    global tx_enabled
    if not body.enabled:
        try:
            await client.send("RIG.TX_HALT")
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    tx_enabled = body.enabled
    return {
        "status": "ok",
        "tx_enabled": tx_enabled,
        "scope": "js8link",
        "halted": not body.enabled,
        "message": "JS8Call TX was halted; its persistent TX_ENABLED setting is read-only via the API.",
    }


@app.get("/api/js8/call-activity", response_model=CallActivityResponse)
async def api_get_call_activity() -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        activity_info = await client.request("RX.GET_CALL_ACTIVITY")
        params = activity_info.get("params") or {}
        # Response has callsign keys with SNR, GRID, UTC values plus _ID
        calls = {k: v for k, v in params.items() if k != "_ID" and isinstance(v, dict)}
        return {"calls": calls}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/js8/os", response_model=OSResponse)
async def api_get_os() -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        os_info = await client.request("STATION.GET_OS")
        params = os_info.get("params") or {}
        return {
            "os_name": params.get("OS_NAME"),
            "os_kernel": params.get("OS_KERNEL"),
            "os_kernel_version": params.get("OS_KERNEL_VERSION"),
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/js8/auto-reply")
async def api_set_auto_reply(body: BoolToggleRequest) -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        await client.send("STATION.SET_AUTO_REPLY", value=str(body.enabled).lower())
        return {"status": "ok", "auto_reply": body.enabled}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/js8/js8hb")
async def api_set_js8hb(body: BoolToggleRequest) -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        await client.send("STATION.SET_JS8HB", value=str(body.enabled).lower())
        return {"status": "ok", "js8hb": body.enabled}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/js8/hback")
async def api_set_hback(body: BoolToggleRequest) -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        await client.send("STATION.SET_HBACK", value=str(body.enabled).lower())
        return {"status": "ok", "hback": body.enabled}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/js8/multi-decoder")
async def api_set_multi_decoder(body: BoolToggleRequest) -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        await client.send("STATION.SET_MULTI_DECODER", value=str(body.enabled).lower())
        return {"status": "ok", "multi_decoder": body.enabled}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/js8/avoid-allcall")
async def api_set_avoid_allcall(body: BoolToggleRequest) -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        await client.send("STATION.SET_AVOID_ALLCALL", value=str(body.enabled).lower())
        return {"status": "ok", "avoid_allcall": body.enabled}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/js8/hb-interval")
async def api_set_hb_interval(body: HbIntervalRequest) -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        await client.send("STATION.SET_HB_INTERVAL", params={"INTERVAL": body.interval})
        return {"status": "ok", "interval": body.interval}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/js8/send-hb")
async def api_send_hb() -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    if not tx_enabled:
        raise HTTPException(status_code=409, detail="TX is disabled in JS8Link")
    try:
        tx_state["pending_heartbeat_beacon"] = {
            "text": f"{local_callsign or 'TX'} @HB HEARTBEAT",
            "queued_at": utcnow(),
        }
        await client.send("STATION.SEND_HB")
        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/js8/hb-timer")
async def api_set_hb_timer(body: BoolToggleRequest) -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    if body.enabled and not tx_enabled:
        raise HTTPException(status_code=409, detail="TX is disabled in JS8Link")
    try:
        await client.send("STATION.SET_HB_TIMER", value=str(body.enabled).lower())
        return {"status": "ok", "hb_timer_active": body.enabled}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Activity
# ---------------------------------------------------------------------------
def _diagnostic_summary(trace: DiagnosticTrace) -> dict[str, Any]:
    summary = trace.summary
    interpretation = trace.interpretation
    if trace.source in {"js8_api", "automatic_task"}:
        try:
            raw_message = json.loads(trace.raw_payload or "{}")
            if isinstance(raw_message, dict):
                meaning = describe_api_message(
                    raw_message,
                    is_response=trace.source == "js8_api",
                    outbound=trace.source == "automatic_task",
                )
                summary, interpretation = meaning.summary, meaning.interpretation
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    return {
        "trace_id": trace.trace_id,
        "source": trace.source,
        "event_type": trace.event_type,
        "severity": trace.severity,
        "summary": summary,
        "interpretation": interpretation,
        "created_at": trace.created_at,
    }


@app.get("/api/diagnostics/traces", response_model=DiagnosticTraceListResponse)
async def api_diagnostic_traces(
    limit: int = Query(default=200, ge=1, le=500),
    source: str | None = Query(default=None, max_length=32),
    severity: str | None = Query(default=None, max_length=16),
    search: str | None = Query(default=None, max_length=120),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return compact traces for the diagnostics timeline."""
    query = select(DiagnosticTrace).order_by(desc(DiagnosticTrace.created_at)).limit(limit)
    if source:
        query = query.where(DiagnosticTrace.source == source)
    if severity:
        query = query.where(DiagnosticTrace.severity == severity)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(
            or_(
                DiagnosticTrace.summary.ilike(pattern),
                DiagnosticTrace.interpretation.ilike(pattern),
                DiagnosticTrace.event_type.ilike(pattern),
            )
        )
    traces = (await session.scalars(query)).all()
    return {"traces": [_diagnostic_summary(trace) for trace in traces]}


@app.get("/api/diagnostics/traces/{trace_id}", response_model=DiagnosticTraceDetailResponse)
async def api_diagnostic_trace_detail(
    trace_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    trace = await session.scalar(select(DiagnosticTrace).where(DiagnosticTrace.trace_id == trace_id))
    if trace is None:
        raise HTTPException(status_code=404, detail="Diagnostic trace not found")
    processing = (
        await session.scalars(
            select(DiagnosticProcessing)
            .where(DiagnosticProcessing.trace_id == trace_id)
            .order_by(DiagnosticProcessing.sequence, DiagnosticProcessing.id)
        )
    ).all()
    return {
        **_diagnostic_summary(trace),
        "raw_payload": trace.raw_payload,
        "processing": [
            {
                "id": entry.id,
                "sequence": entry.sequence,
                "operation": entry.operation,
                "outcome": entry.outcome,
                "detail": entry.detail,
                "payload": entry.payload,
                "created_at": entry.created_at,
            }
            for entry in processing
        ],
    }


@app.post("/api/diagnostics/purge", response_model=PurgeResponse)
async def api_purge_diagnostics(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Remove diagnostic traces only; radio and user configuration remain intact."""
    processing = await session.execute(delete(DiagnosticProcessing))
    traces = await session.execute(delete(DiagnosticTrace))
    await session.commit()
    return {
        "status": "ok",
        "deleted": {
            "diagnostic_processing": int(getattr(processing, "rowcount", 0) or 0),
            "diagnostic_traces": int(getattr(traces, "rowcount", 0) or 0),
        },
    }


@app.get("/api/activity")
async def api_activity(
    limit: int = Query(default=200, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    result = await session.scalars(select(ActivityEvent).order_by(desc(ActivityEvent.created_at)).limit(limit))
    return [
        {
            "id": evt.id,
            "event_type": evt.event_type,
            "payload": evt.payload,
            "created_at": evt.created_at.isoformat() if evt.created_at else None,
        }
        for evt in result
    ]


# ---------------------------------------------------------------------------
# Messages (received)
# ---------------------------------------------------------------------------
@app.get("/api/messages")
async def api_messages(
    callsign: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    before_id: int | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    query = select(ReceivedMessage).order_by(desc(ReceivedMessage.received_at))
    if callsign:
        query = query.where(
            or_(
                ReceivedMessage.callsign == callsign,
                ReceivedMessage.from_callsign == callsign,
            )
        )
    if before_id is not None:
        query = query.where(ReceivedMessage.id < before_id)
    query = query.limit(limit)
    result = await session.scalars(query)
    return [
        {
            "id": msg.id,
            "callsign": msg.callsign,
            "text": msg.text,
            "kind": msg.kind,
            "delivery_mode": msg.delivery_mode,
            "protocol_id": msg.protocol_id,
            "message_type": msg.message_type,
            "grid": msg.grid,
            "frequency": msg.frequency,
            "offset": msg.offset,
            "band": msg.band,
            "mode": msg.mode,
            "snr": msg.snr,
            "from_callsign": msg.from_callsign,
            "to_callsign": msg.to_callsign,
            "command": msg.command,
            "is_heartbeat": msg.is_heartbeat,
            "utc_timestamp": msg.utc_timestamp.isoformat() if msg.utc_timestamp else None,
            "received_at": msg.received_at.isoformat() if msg.received_at else None,
        }
        for msg in result
    ]


# ---------------------------------------------------------------------------
# Monitor endpoints
# ---------------------------------------------------------------------------
@app.get("/api/monitor")
async def api_monitor(
    kind: str | None = Query(default=None),
    band: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    query = select(ReceivedMessage).order_by(desc(ReceivedMessage.received_at))
    if kind:
        query = query.where(ReceivedMessage.kind == kind)
    if band:
        query = query.where(ReceivedMessage.band == band)
    query = query.limit(limit)
    result = await session.scalars(query)
    return [
        {
            "id": msg.id,
            "callsign": msg.callsign,
            "sender_source": msg.sender_source,
            "kind": msg.kind,
            "text": msg.text,
            "band": msg.band,
            "mode": msg.mode,
            "snr": msg.snr,
            "offset": msg.offset,
            "frequency": msg.frequency,
            "from_callsign": msg.from_callsign,
            "to_callsign": msg.to_callsign,
            "is_heartbeat": msg.is_heartbeat,
            "received_at": msg.received_at.isoformat() if msg.received_at else None,
        }
        for msg in result
    ]


async def _monitor_traffic_items(
    session: AsyncSession,
    minutes: int = 1440,
    band: str | None = None,
) -> list[dict[str, Any]]:
    """Return the unified RX/TX traffic shape used by the station console."""
    def event_type_for_message(message: ReceivedMessage) -> str:
        event_type = str(message.message_type or "").upper()
        if event_type not in {"RX", "TX"}:
            return event_type or "RX.ACTIVITY"
        return {
            "band_activity": "RX.BAND_ACTIVITY",
            "heartbeat": "RX.BAND_ACTIVITY",
            "direct_message": "RX.DIRECTED",
            "directed_control": "RX.DIRECTED",
        }.get(message.kind or "", "RX.ACTIVITY")

    cutoff = utcnow() - timedelta(minutes=minutes)
    rx_query = select(ReceivedMessage).order_by(desc(ReceivedMessage.received_at))
    rx_query = rx_query.where(ReceivedMessage.received_at >= cutoff)
    if band:
        rx_query = rx_query.where(ReceivedMessage.band == band)
    received = (await session.scalars(rx_query.limit(5000))).all()

    tx_query = select(TransmittedMessage).order_by(desc(TransmittedMessage.transmitted_at))
    tx_query = tx_query.where(TransmittedMessage.transmitted_at >= cutoff)
    if band:
        tx_query = tx_query.where(TransmittedMessage.band == band)
    transmitted = (await session.scalars(tx_query.limit(2000))).all()
    items = []
    for message in received:
        display_timestamp = message.utc_timestamp or message.received_at
        sender = message.from_callsign or message.callsign
        if not sender:
            # Older activity rows were stored before callsign extraction was
            # applied. Reconstruct their sender at read time so existing
            # history does not remain stuck on "Unknown".
            sender, _ = extract_activity_sender_and_text(message.sender_source or message.text)
        items.append(
            {
                "id": message.id,
                "sender": sender or "Unknown",
                "sender_source": message.sender_source,
                "recipient": message.to_callsign,
                "text": message.text,
                "type": event_type_for_message(message),
                "command": message.command,
                "grid": message.grid,
                "snr": message.snr,
                "offset": message.offset,
                "mode": message.mode,
                "band": message.band,
                "is_heartbeat": message.is_heartbeat,
                "received_at": display_timestamp.isoformat(),
                "kind": message.kind,
                "direction": "rx",
            }
        )
    items.extend(
        {
            "id": -message.id,
            "sender": local_callsign or "TX",
            "sender_source": "api",
            "recipient": message.callsign,
            "text": message.text,
            "type": "HEARTBEAT" if "HEARTBEAT" in (message.text or "").upper() else "TX.FRAME",
            "snr": None,
            "offset": message.offset,
            "mode": message.mode,
            "band": message.band,
            "is_heartbeat": "HEARTBEAT" in (message.text or "").upper(),
            "received_at": message.transmitted_at.isoformat(),
            "kind": "direct_message",
            "direction": "tx",
        }
        for message in transmitted
    )
    return sorted(items, key=lambda item: item["received_at"], reverse=True)


@app.get("/api/monitor/messages")
async def api_monitor_messages_compat(
    minutes: int = Query(default=1440, ge=15, le=10080),
    band: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Compatibility response for web clients using the richer monitor model."""
    return {"messages": await _monitor_traffic_items(session, minutes=minutes, band=band)}


@app.get("/api/monitor/spectrum")
async def api_monitor_spectrum(
    minutes: int | None = Query(default=None, ge=1, le=1440),
    band: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return recent offset occupancy for the compact station-console band scope.

    The time window defaults to the configurable ``band_scope_minutes`` setting
    (from preferences) when no explicit ``minutes`` parameter is supplied.
    """
    if minutes is None:
        config = await _get_app_config(session)
        minutes = max(1, min(config.band_scope_minutes, 1440))

    if client and client.connected:
        try:
            # Lightly refresh the cached snapshot so the band scope shows
            # current activity, but do NOT call _handle_activity here — the
            # real-time RX.ACTIVITY / RX.DIRECTED event handlers are the
            # canonical source for persisted monitor traffic.  Turning the
            # snapshot into ReceivedMessage rows on every poll would re-create
            # data that was intentionally purged.
            await _get_band_activity_snapshot()
        except Exception:
            logger.debug("Could not refresh the JS8Call band-activity snapshot", exc_info=True)

    cutoff = utcnow() - timedelta(minutes=minutes)
    all_signals: list[dict[str, Any]] = []
    for item in await _monitor_traffic_items(session, minutes=minutes, band=band):
        offset = item.get("offset")
        if offset is None or not 500 <= int(offset) <= 2500:
            continue
        if datetime.fromisoformat(item["received_at"]) < cutoff:
            continue
        if band and item.get("band") != band:
            continue
        all_signals.append(
            {
                "offset": int(offset),
                "callsign": item["sender"],
                "snr": item.get("snr"),
                "direction": item["direction"],
                "mode": item.get("mode"),
                "received_at": item["received_at"],
            }
        )

    # Show every signal in the time window, sorted by offset.  More than one
    # signal can share the same offset bucket; they are drawn as overlapping
    # lines so the busiest offsets look taller, giving a natural waterfall feel.
    return {
        "minimum_offset": 500,
        "maximum_offset": 2500,
        "signals": sorted(all_signals, key=lambda s: s["offset"]),
    }


@app.get("/api/monitor/band-activity")
async def api_monitor_band_activity_compat(
    minutes: int = Query(default=1440, ge=15, le=1440),
    band: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    cutoff = utcnow() - timedelta(minutes=minutes)
    items = [
        item
        for item in await _monitor_traffic_items(session, minutes=minutes, band=band)
        if datetime.fromisoformat(item["received_at"]) >= cutoff
        and (not band or item.get("band") == band)
    ]
    grouped: dict[int | None, list[dict[str, Any]]] = {}
    for item in items:
        raw_offset = item.get("offset")
        offset = int(raw_offset) if raw_offset is not None else None
        grouped.setdefault(offset, []).append(
            {
                "id": item["id"],
                "callsign": item["sender"],
                "sender_source": item.get("sender_source"),
                "text": item["text"],
                "snr": item.get("snr"),
                "offset": item.get("offset"),
                "mode": item.get("mode"),
                "band": item.get("band"),
                "received_at": item["received_at"],
                "kind": item.get("kind"),
                "direction": item["direction"],
            }
        )
    return {
        "groups": [
            {"offset": offset, "messages": messages, "count": len(messages)}
            for offset, messages in sorted(grouped.items(), key=lambda item: (item[0] is None, item[0] or 0))
        ]
    }


@app.get("/api/monitor/last-heard")
async def api_monitor_last_heard_compat(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    stations = (await session.scalars(select(Station).order_by(desc(Station.last_seen)).limit(1000))).all()
    transmitted = (
        await session.scalars(select(TransmittedMessage).where(TransmittedMessage.callsign.is_not(None)))
    ).all()
    own_station = next((station for station in stations if station.callsign == local_callsign), None)
    own_coordinates = (
        (own_station.latitude, own_station.longitude)
        if own_station and own_station.latitude is not None and own_station.longitude is not None
        else None
    )
    current = now()
    station_items = {
        station.callsign: {
            "callsign": station.callsign,
            "grid": station.grid,
            "heard_seconds_ago": max(0, int((current - station.last_seen).total_seconds())),
            "last_snr": station.last_snr,
            "last_offset": station.last_offset,
            "last_mode": station.last_mode,
            "last_tdrift": station.last_tdrift,
            "distance_km": (
                round(
                    great_circle_distance_km(
                        own_coordinates,
                        (station.latitude, station.longitude),
                    )
                )
                if own_coordinates and station.latitude is not None and station.longitude is not None
                else None
            ),
            "last_seen": station.last_seen.isoformat(),
            "band": None,
            "direction": "rx",
        }
        for station in stations
    }
    for message in transmitted:
        if not message.callsign:
            continue
        timestamp = message.transmitted_at
        current_item = station_items.get(message.callsign)
        if current_item and current_item["last_seen"] >= timestamp.isoformat():
            continue
        station_items[message.callsign] = {
            "callsign": message.callsign,
            "grid": None,
            "heard_seconds_ago": max(0, int((utcnow() - timestamp).total_seconds())),
            "last_snr": None,
            "last_offset": message.offset,
            "last_mode": message.mode,
            "last_tdrift": None,
            "distance_km": None,
            "last_seen": timestamp.isoformat(),
            "band": message.band,
            "direction": "tx",
        }
    return {
        "stations": [
            item
            for item in sorted(station_items.values(), key=lambda value: value["last_seen"], reverse=True)
        ]
    }


@app.get("/api/monitor/graph")
async def api_monitor_graph_compat(
    minutes: int = Query(default=1440, ge=15, le=1440),
    band: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    cutoff = utcnow() - timedelta(minutes=minutes)
    station_rows = list((await session.scalars(select(Station).where(Station.last_seen >= cutoff))).all())
    if local_callsign and not any(station.callsign == local_callsign for station in station_rows):
        own_station = await session.scalar(select(Station).where(Station.callsign == local_callsign))
        if own_station is None and client and client.connected:
            grid = await _station_text(client, "STATION.GET_GRID")
            own_station = await _ensure_local_station(session, local_callsign, grid)
            await session.commit()
        if own_station is not None:
            station_rows.append(own_station)
    station_map = {station.id: station for station in station_rows}
    link_rows = (await session.scalars(select(StationLink).where(StationLink.last_seen >= cutoff))).all()
    if band:
        link_rows = [link for link in link_rows if link.band == band]

    pairs: dict[tuple[int, int], dict[str, Any]] = {}
    for link in link_rows:
        source = station_map.get(link.source_station_id)
        target = station_map.get(link.target_station_id)
        if not source or not target:
            continue
        pair_key = (min(source.id, target.id), max(source.id, target.id))
        entry = pairs.setdefault(
            pair_key,
            {
                "id": link.id,
                "source": source.callsign,
                "target": target.callsign,
                "source_latitude": source.latitude,
                "source_longitude": source.longitude,
                "target_latitude": target.latitude,
                "target_longitude": target.longitude,
                # These fields are endpoint-oriented: they describe the SNR
                # at the station named by the corresponding endpoint.  The
                # older forward/reverse fields are kept below for API
                # compatibility, but must not be used to choose a line half.
                "snr_at_source": None,
                "snr_at_target": None,
                "observations_at_source": 0,
                "observations_at_target": 0,
                "snr_forward": None,
                "snr_reverse": None,
                "forward_observations": 0,
                "reverse_observations": 0,
                "observation_count": 0,
                "distance_km": (
                    round(
                        great_circle_distance_km(
                            (source.latitude, source.longitude),
                            (target.latitude, target.longitude),
                        )
                    )
                    if source.latitude is not None
                    and source.longitude is not None
                    and target.latitude is not None
                    and target.longitude is not None
                    else None
                ),
                "last_seen": link.last_seen.isoformat(),
            },
        )
        endpoint_known = link.relation_type in {"heartbeat", "hearing"}
        is_source_endpoint = entry["source"] == source.callsign
        if endpoint_known:
            entry["snr_at_source" if is_source_endpoint else "snr_at_target"] = link.latest_snr
            observation_key = (
                "observations_at_source" if is_source_endpoint else "observations_at_target"
            )
            entry[observation_key] += link.observation_count
        # Preserve the historical fields for clients that still consume them.
        entry["snr_forward" if is_source_endpoint else "snr_reverse"] = link.latest_snr
        entry["forward_observations" if is_source_endpoint else "reverse_observations"] += link.observation_count
        entry["observation_count"] += link.observation_count
        if link.last_seen.isoformat() > entry["last_seen"]:
            entry["last_seen"] = link.last_seen.isoformat()

    # Reconstruct recent heartbeat relations from stored monitor traffic as a
    # fallback. This keeps the map useful when a heartbeat was stored before
    # the StationLink row could be updated (for example after a reconnect or
    # an older database migration).
    heartbeat_rows = (
        await session.scalars(
            select(ReceivedMessage).where(
                ReceivedMessage.is_heartbeat.is_(True),
                ReceivedMessage.received_at >= cutoff,
            )
        )
    ).all()
    heartbeat_pattern = re.compile(
        r"\b([A-Z0-9/]+):?\s+([A-Z0-9/]+)\s+HEARTBEAT\s+SNR\s+(-?\d+)\b",
        re.IGNORECASE,
    )
    station_by_callsign = {station.callsign: station for station in station_map.values()}
    for heartbeat in heartbeat_rows:
        if band and heartbeat.band != band:
            continue
        text = heartbeat.text.upper()
        match = heartbeat_pattern.search(text)
        if not match:
            continue
        source_callsign, target_callsign, snr_text = match.groups()
        source = station_by_callsign.get(source_callsign)
        target = station_by_callsign.get(target_callsign)
        if source is None or target is None or source.id == target.id:
            continue
        pair_key = (min(source.id, target.id), max(source.id, target.id))
        entry = pairs.get(pair_key)
        snr = int(snr_text)
        if entry is None:
            entry = {
                "id": -heartbeat.id,
                "source": source.callsign,
                "target": target.callsign,
                "source_latitude": source.latitude,
                "source_longitude": source.longitude,
                "target_latitude": target.latitude,
                "target_longitude": target.longitude,
                "snr_at_source": snr,
                "snr_at_target": None,
                "observations_at_source": 1,
                "observations_at_target": 0,
                "snr_forward": snr,
                "snr_reverse": None,
                "forward_observations": 1,
                "reverse_observations": 0,
                "observation_count": 1,
                "distance_km": (
                    round(
                        great_circle_distance_km(
                            (source.latitude, source.longitude),
                            (target.latitude, target.longitude),
                        )
                    )
                    if source.latitude is not None
                    and source.longitude is not None
                    and target.latitude is not None
                    and target.longitude is not None
                    else None
                ),
                "last_seen": heartbeat.received_at.isoformat(),
            }
            pairs[pair_key] = entry
            continue
        if entry["source"] == source.callsign:
            entry["snr_at_source"] = snr
            entry["observations_at_source"] += 1
            entry["snr_forward"] = snr
            entry["forward_observations"] += 1
        else:
            entry["snr_at_target"] = snr
            entry["observations_at_target"] += 1
            entry["snr_reverse"] = snr
            entry["reverse_observations"] += 1
        entry["observation_count"] += 1
        if heartbeat.received_at.isoformat() > entry["last_seen"]:
            entry["last_seen"] = heartbeat.received_at.isoformat()

    # A station that we decode is also a reliable one-way path to our own
    # station.  Not every decode is a heartbeat, so create the missing local
    # leg from the latest received SNR.  This prevents map nodes without a
    # corresponding path while still keeping explicitly observed station-to-
    # station heartbeat relations intact.
    recent_receptions: dict[tuple[str, str | None], ReceivedMessage] = {}
    received_rows = (
        await session.scalars(
            select(ReceivedMessage)
            .where(ReceivedMessage.received_at >= cutoff)
            .order_by(desc(ReceivedMessage.received_at))
        )
    ).all()
    for received in received_rows:
        callsign = (received.from_callsign or received.callsign or "").strip().upper()
        if not callsign or callsign == local_callsign or received.snr is None:
            continue
        message_band = received.band
        if band and message_band != band:
            continue
        key = (callsign, message_band)
        recent_receptions.setdefault(key, received)

    if local_callsign:
        own_station = station_by_callsign.get(local_callsign)
        if own_station is not None:
            for station in station_map.values():
                if station.callsign == local_callsign:
                    continue
                reception = recent_receptions.get((station.callsign, band))
                if reception is None and not band:
                    reception = next(
                        (
                            item
                            for (callsign, _), item in recent_receptions.items()
                            if callsign == station.callsign
                        ),
                        None,
                    )
                if reception is None:
                    continue
                pair_key = (min(own_station.id, station.id), max(own_station.id, station.id))
                entry = pairs.get(pair_key)
                if entry is None:
                    entry = {
                        "id": -station.id,
                        "source": station.callsign,
                        "target": own_station.callsign,
                        "source_latitude": station.latitude,
                        "source_longitude": station.longitude,
                        "target_latitude": own_station.latitude,
                        "target_longitude": own_station.longitude,
                        # The local station is the receiver for this decode,
                        # so its SNR belongs to the target endpoint.  The
                        # remote endpoint is not known to hear us yet.
                        "snr_at_source": None,
                        "snr_at_target": reception.snr,
                        "observations_at_source": 0,
                        "observations_at_target": 1,
                        "snr_forward": None,
                        "snr_reverse": None,
                        "forward_observations": 0,
                        "reverse_observations": 0,
                        "observation_count": 1,
                        "distance_km": (
                            round(
                                great_circle_distance_km(
                                    (station.latitude, station.longitude),
                                    (own_station.latitude, own_station.longitude),
                                )
                            )
                            if station.latitude is not None
                            and station.longitude is not None
                            and own_station.latitude is not None
                            and own_station.longitude is not None
                            else None
                        ),
                        "last_seen": reception.received_at.isoformat(),
                    }
                    pairs[pair_key] = entry
                elif entry["target"] == own_station.callsign and entry["source"] == station.callsign:
                    entry["snr_at_target"] = reception.snr
                    entry["observations_at_target"] += 1
                    entry["snr_reverse"] = reception.snr
                    entry["reverse_observations"] += 1
                elif entry["source"] == own_station.callsign and entry["target"] == station.callsign:
                    entry["snr_at_source"] = reception.snr
                    entry["observations_at_source"] += 1
                    entry["snr_forward"] = reception.snr
                    entry["forward_observations"] += 1
                elif entry["source"] == station.callsign and entry["snr_at_source"] is None:
                    entry["snr_at_source"] = reception.snr
                    entry["observations_at_source"] += 1
                    entry["snr_forward"] = reception.snr
                    entry["forward_observations"] += 1
                elif entry["target"] == station.callsign and entry["snr_at_target"] is None:
                    entry["snr_at_target"] = reception.snr
                    entry["observations_at_target"] += 1
                    entry["snr_reverse"] = reception.snr
                    entry["reverse_observations"] += 1
                if reception.received_at.isoformat() > entry["last_seen"]:
                    entry["last_seen"] = reception.received_at.isoformat()

    links = list(pairs.values())
    linked_station_ids = {
        station.id
        for link in links
        for station in (
            station_by_callsign.get(link["source"]),
            station_by_callsign.get(link["target"]),
        )
        if station is not None
    }
    for link in links:
        link["label"] = f"{link['source']} ↔ {link['target']}"
        link["bidirectional"] = (
            link.get("snr_at_source") is not None
            and link.get("snr_at_target") is not None
        )
    return {
        "stations": [
            {
                "id": station.id,
                "callsign": station.callsign,
                "grid": station.grid,
                "latitude": station.latitude,
                "longitude": station.longitude,
                "country": station.country,
                "location_source": station.location_source,
                "last_snr": station.last_snr,
                "last_offset": station.last_offset,
                "last_mode": station.last_mode,
                "message_count": station.message_count,
                "last_seen": station.last_seen.isoformat(),
            }
            for station in station_rows
            if station.id in linked_station_ids
        ],
        "links": links,
    }


@app.get("/api/monitor/stations")
async def api_monitor_stations(
    limit: int = Query(default=200, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    result = await session.scalars(select(Station).order_by(desc(Station.last_seen)).limit(limit))
    return [
        {
            "id": sta.id,
            "callsign": sta.callsign,
            "name": sta.name,
            "qth": sta.qth,
            "grid": sta.grid,
            "latitude": sta.latitude,
            "longitude": sta.longitude,
            "country": sta.country,
            "location_source": sta.location_source,
            "first_seen": sta.first_seen.isoformat() if sta.first_seen else None,
            "last_seen": sta.last_seen.isoformat() if sta.last_seen else None,
            "last_snr": sta.last_snr,
            "message_count": sta.message_count,
            "last_offset": sta.last_offset,
            "last_mode": sta.last_mode,
        }
        for sta in result
    ]


@app.get("/api/monitor/stations/{callsign}")
async def api_monitor_station_detail(
    callsign: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    result = await session.scalars(select(Station).where(Station.callsign == callsign.upper()))
    station = result.one_or_none()
    if station is None:
        raise HTTPException(status_code=404, detail="Station not found")

    # Get recent messages from this station
    messages_result = await session.scalars(
        select(ReceivedMessage)
        .where(
            or_(
                ReceivedMessage.callsign == callsign.upper(),
                ReceivedMessage.from_callsign == callsign.upper(),
            )
        )
        .order_by(desc(ReceivedMessage.received_at))
        .limit(50)
    )

    # Get station links
    links_result = await session.scalars(
        select(StationLink).where(
            or_(
                StationLink.source_station_id == station.id,
                StationLink.target_station_id == station.id,
            )
        )
    )

    link_ids = {
        link.target_station_id if link.source_station_id == station.id else link.source_station_id
        for link in links_result
    }
    linked_stations_result = await session.scalars(select(Station).where(Station.id.in_(link_ids)))
    linked_map = {s.id: s for s in linked_stations_result}

    return {
        "id": station.id,
        "callsign": station.callsign,
        "name": station.name,
        "qth": station.qth,
        "notes": station.notes,
        "grid": station.grid,
        "latitude": station.latitude,
        "longitude": station.longitude,
        "country": station.country,
        "location_source": station.location_source,
        "first_seen": station.first_seen.isoformat() if station.first_seen else None,
        "last_seen": station.last_seen.isoformat() if station.last_seen else None,
        "last_snr": station.last_snr,
        "message_count": station.message_count,
        "last_offset": station.last_offset,
        "last_mode": station.last_mode,
        "js8link_version": station.js8link_version,
        "js8link_last_seen": station.js8link_last_seen.isoformat() if station.js8link_last_seen else None,
        "info_text": station.info_text,
        "info_updated_at": station.info_updated_at.isoformat() if station.info_updated_at else None,
        "status_text": station.status_text,
        "status_updated_at": station.status_updated_at.isoformat() if station.status_updated_at else None,
        "hearing_report": json.loads(station.hearing_report) if station.hearing_report else None,
        "hearing_updated_at": station.hearing_updated_at.isoformat() if station.hearing_updated_at else None,
        "grid_source": station.grid_source,
        "last_snr_query_at": station.last_snr_query_at.isoformat() if station.last_snr_query_at else None,
        "last_hearing_query_at": station.last_hearing_query_at.isoformat() if station.last_hearing_query_at else None,
        "last_info_query_at": station.last_info_query_at.isoformat() if station.last_info_query_at else None,
        "last_grid_query_at": station.last_grid_query_at.isoformat() if station.last_grid_query_at else None,
        "last_status_query_at": station.last_status_query_at.isoformat() if station.last_status_query_at else None,
        "recent_messages": [
            {
                "id": msg.id,
                "text": msg.text,
                "kind": msg.kind,
                "snr": msg.snr,
                "received_at": msg.received_at.isoformat() if msg.received_at else None,
            }
            for msg in messages_result
        ],
        "links": [
            {
                "relation_type": link.relation_type,
                "band": link.band,
                "latest_snr": link.latest_snr,
                "average_snr": link.average_snr,
                "best_snr": link.best_snr,
                "observation_count": link.observation_count,
                "linked_callsign": (
                    linked_map[linked_id].callsign
                    if (
                        linked_id := link.target_station_id
                        if link.source_station_id == station.id
                        else link.source_station_id
                    )
                    in linked_map
                    else None
                ),
            }
            for link in links_result
        ],
    }


@app.patch("/api/monitor/stations/{callsign}")
async def api_patch_station(
    callsign: str,
    body: StationContactPatch,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    result = await session.scalars(select(Station).where(Station.callsign == callsign.upper()))
    station = result.one_or_none()
    if station is None:
        raise HTTPException(status_code=404, detail="Station not found")
    if body.name is not None:
        station.name = body.name
    if body.qth is not None:
        station.qth = body.qth
    if body.notes is not None:
        station.notes = body.notes
    await session.commit()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Inbox
# ---------------------------------------------------------------------------
@app.get("/api/inbox")
async def api_inbox(
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    result = await session.scalars(
        select(ReceivedMessage)
        .where(ReceivedMessage.kind.in_(("direct_message", "directed_control")))
        .order_by(desc(ReceivedMessage.received_at))
        .limit(limit)
    )
    return [
        {
            "id": msg.id,
            "callsign": msg.callsign,
            "from_callsign": msg.from_callsign,
            "text": msg.text,
            "kind": msg.kind,
            "delivery_mode": msg.delivery_mode,
            "protocol_id": msg.protocol_id,
            "snr": msg.snr,
            "mode": msg.mode,
            "band": msg.band,
            "command": msg.command,
            "received_at": msg.received_at.isoformat() if msg.received_at else None,
        }
        for msg in result
    ]


# ---------------------------------------------------------------------------
# Outbox
# ---------------------------------------------------------------------------
@app.get("/api/outbox")
async def api_outbox(
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    result = await session.scalars(
        select(TransmittedMessage).order_by(desc(TransmittedMessage.transmitted_at)).limit(limit)
    )
    return [
        {
            "id": msg.id,
            "callsign": msg.callsign,
            "text": msg.text,
            "status": msg.status,
            "delivery_mode": msg.delivery_mode,
            "protocol_id": msg.protocol_id,
            "delivery_status": msg.delivery_status,
            "attempts": msg.attempts,
            "max_attempts": msg.max_attempts,
            "delivered_at": msg.delivered_at.isoformat() if msg.delivered_at else None,
            "last_error": msg.last_error,
            "band": msg.band,
            "offset": msg.offset,
            "mode": msg.mode,
            "transmitted_at": msg.transmitted_at.isoformat() if msg.transmitted_at else None,
            "confirmed_at": msg.confirmed_at.isoformat() if msg.confirmed_at else None,
        }
        for msg in result
    ]


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------
@app.get("/api/graph")
async def api_graph(
    min_snr: int = Query(default=-30),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    result = await session.scalars(select(StationLink).where(StationLink.latest_snr >= min_snr))
    links = result.all()

    station_ids = {link.source_station_id for link in links} | {link.target_station_id for link in links}
    stations_result = await session.scalars(select(Station).where(Station.id.in_(station_ids)))
    station_map = {s.id: s for s in stations_result}

    nodes = [
        {
            "id": sta.callsign,
            "callsign": sta.callsign,
            "name": sta.name,
            "grid": sta.grid,
            "latitude": sta.latitude,
            "longitude": sta.longitude,
            "country": sta.country,
            "last_seen": sta.last_seen.isoformat() if sta.last_seen else None,
            "message_count": sta.message_count,
        }
        for sta in station_map.values()
    ]

    edges = [
        {
            "source": station_map[link.source_station_id].callsign,
            "target": station_map[link.target_station_id].callsign,
            "relation_type": link.relation_type,
            "band": link.band,
            "latest_snr": link.latest_snr,
            "average_snr": link.average_snr,
            "best_snr": link.best_snr,
            "observation_count": link.observation_count,
        }
        for link in links
        if link.source_station_id in station_map and link.target_station_id in station_map
    ]

    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------
@app.get("/api/preferences", response_model=PreferencesResponse)
async def api_get_preferences(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    config = await _get_app_config(session)
    return {
        "language": config.language,
        "theme": config.theme,
        "time_display": config.time_display,
        "monitor_band": config.monitor_band,
        "monitor_sort_key": config.monitor_sort_key,
        "monitor_sort_direction": config.monitor_sort_direction,
        "monitor_map_height": config.monitor_map_height,
        "monitor_map_center_latitude": config.monitor_map_center_latitude,
        "monitor_map_center_longitude": config.monitor_map_center_longitude,
        "monitor_map_zoom": config.monitor_map_zoom,
        "monitor_map_popups": config.monitor_map_popups,
        "monitor_map_greyline": config.monitor_map_greyline,
        "monitor_map_bidirectional_only": config.monitor_map_bidirectional_only,
        "monitor_map_cluster_stations": config.monitor_map_cluster_stations,
        "toast_duration_seconds": config.toast_duration_seconds,
        "monitor_view": config.monitor_view,
        "selected_chat_callsign": config.selected_chat_callsign,
        "history_minutes": config.map_history_minutes,
        "received_message_retention_days": config.received_message_retention_days,
        "band_scope_minutes": config.band_scope_minutes,
    }


@app.patch("/api/preferences")
async def api_patch_preferences(
    body: UIPreferencesPatch,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    config = await _get_app_config(session)
    if body.language is not None:
        config.language = body.language
    if body.theme is not None:
        config.theme = body.theme
    if body.time_display is not None:
        config.time_display = body.time_display
    if body.monitor_band is not None:
        config.monitor_band = body.monitor_band
    if body.monitor_sort_key is not None:
        config.monitor_sort_key = body.monitor_sort_key
    if body.monitor_sort_direction is not None:
        config.monitor_sort_direction = body.monitor_sort_direction
    if body.monitor_map_height is not None:
        config.monitor_map_height = body.monitor_map_height
    if body.monitor_map_center_latitude is not None:
        config.monitor_map_center_latitude = body.monitor_map_center_latitude
    if body.monitor_map_center_longitude is not None:
        config.monitor_map_center_longitude = body.monitor_map_center_longitude
    if body.monitor_map_zoom is not None:
        config.monitor_map_zoom = body.monitor_map_zoom
    if body.monitor_map_popups is not None:
        config.monitor_map_popups = body.monitor_map_popups
    if body.monitor_map_greyline is not None:
        config.monitor_map_greyline = body.monitor_map_greyline
    if body.monitor_map_bidirectional_only is not None:
        config.monitor_map_bidirectional_only = body.monitor_map_bidirectional_only
    if body.monitor_map_cluster_stations is not None:
        config.monitor_map_cluster_stations = body.monitor_map_cluster_stations
    if body.monitor_view is not None:
        config.monitor_view = body.monitor_view
    if body.selected_chat_callsign is not None:
        config.selected_chat_callsign = body.selected_chat_callsign
    if body.history_minutes is not None:
        config.map_history_minutes = body.history_minutes
    if body.received_message_retention_days is not None:
        config.received_message_retention_days = body.received_message_retention_days
    if body.band_scope_minutes is not None:
        config.band_scope_minutes = body.band_scope_minutes
    await session.commit()
    return {"status": "ok"}


@app.post("/api/data/purge", response_model=PurgeResponse)
async def api_purge_data(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Delete operational history while preserving all user configuration."""
    tables = (
        (DiagnosticProcessing, "diagnostic_processing"),
        (DiagnosticTrace, "diagnostic_traces"),
        (ArqReceipt, "arq_receipts"),
        (StationQuery, "station_queries"),
        (StationLink, "station_links"),
        (ReceivedMessage, "received_messages"),
        (TransmittedMessage, "transmitted_messages"),
        (ActivityEvent, "activity_events"),
        (JS8APIMessage, "js8_api_messages"),
        (ChatReadState, "chat_read_state"),
        (Station, "stations"),
    )
    deleted: dict[str, int] = {}
    for model, name in tables:
        result = await session.execute(delete(model))
        deleted[name] = int(getattr(result, "rowcount", 0) or 0)
    await session.commit()
    return {"status": "ok", "deleted": deleted}


# ---------------------------------------------------------------------------
# Map preferences
# ---------------------------------------------------------------------------
@app.patch("/api/preferences/map")
async def api_patch_map_preferences(
    body: MapPreferencesPatch,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    config = await _get_app_config(session)
    if body.history_minutes:
        config.map_history_minutes = body.history_minutes
    await session.commit()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Send message
# ---------------------------------------------------------------------------
@app.post("/api/send")
@app.post("/api/messages/send", response_model=SendMessageResponse)
async def api_send_message(
    body: MessageRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    if not tx_enabled:
        raise HTTPException(status_code=409, detail="TX is disabled in JS8Link")

    text = body.text.strip()
    callsign = (body.callsign or "").strip().upper() if body.callsign else None

    # Group destinations (@HB, @ALLCALL, etc.) only support best-effort.
    # ARQ confirmed delivery to groups would not have a single receiver.
    delivery_mode = body.delivery_mode
    if callsign and callsign.startswith("@"):
        delivery_mode = "best_effort"

    if delivery_mode == "confirmed":
        if callsign:
            active = await session.scalar(
                select(TransmittedMessage).where(
                    TransmittedMessage.callsign == callsign,
                    TransmittedMessage.delivery_mode == "confirmed",
                    TransmittedMessage.delivery_status.in_(("awaiting_ack", "retrying")),
                )
            )
            if active is not None:
                raise HTTPException(status_code=409, detail="A confirmed delivery is already in flight")

        protocol_id = new_message_id()
        wire_text = encode_data(text, protocol_id)
        delivery_status = "transmitting"
        max_attempts = 3
        ack_deadline = None
    else:
        protocol_id = None
        wire_text = text
        delivery_status = None
        max_attempts = 1
        ack_deadline = None

    # Get current radio context
    band_val = None
    offset_val = None
    mode_val = "Normal"
    try:
        context = await _radio_context(client)
        dial = context.get("dial")
        offset_val = context.get("offset")
        speed = context.get("speed")
        band_val = band_from_frequency(dial)
        mode_val = mode_from_speed(speed) or "Normal"
    except Exception:
        pass

    entry = TransmittedMessage(
        callsign=callsign,
        text=text,
        status="queued",
        delivery_mode=body.delivery_mode,
        protocol_id=protocol_id,
        protocol_version=ARQ_VERSION if body.delivery_mode == "confirmed" else None,
        delivery_status=delivery_status,
        attempts=1,
        max_attempts=max_attempts,
        ack_deadline=ack_deadline,
        band=band_val,
        offset=offset_val,
        mode=mode_val,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)

    try:
        selection_lock = transmit_locks.setdefault("__selection__", asyncio.Lock())
        async with selection_lock:
            if callsign:
                sel_info = await client.request("RX.GET_CALL_SELECTED")
                selected = str(sel_info.get("value") or "").strip().upper() or None
                if selected != callsign:
                    await wait_for_tx_buffer_empty(client)
                    await client.send("RX.CALL_SELECTED", value=callsign)
                await transmit_js8_text(client, f"{callsign} {wire_text}", peer=callsign)
            else:
                await transmit_js8_text(client, wire_text)
        entry.status = "sent"
        await _restore_chat_on_activity(session, callsign)
        await session.commit()

        # Set initial tx_state for progress tracking
        tx_state["message"] = wire_text
        tx_state["frames_sent"] = 0
        text_len = len(wire_text)
        tx_state["estimated_frames"] = max((text_len // 22) + (1 if text_len % 22 else 0), 1)
    except Exception as exc:
        entry.status = "failed"
        entry.last_error = str(exc)
        await session.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # Broadcast for real-time UI
    if callsign:
        await broadcast(
            event="chat.message.sent",
            data={
                "callsign": callsign,
                "text": text,
                "protocol_id": protocol_id,
                "delivery_mode": body.delivery_mode,
            },
        )

    return {
        "id": entry.id,
        "status": entry.status,
        "protocol_id": protocol_id,
        "delivery_mode": body.delivery_mode,
        "delivery_status": entry.delivery_status,
    }


# ---------------------------------------------------------------------------
# Store (store-and-forward)
# ---------------------------------------------------------------------------
@app.post("/api/store")
@app.post("/api/messages/store")
async def api_store_message(
    body: MessageRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Store a message for later transmission (store-and-forward)."""
    text = body.text.strip()
    callsign = (body.callsign or "").strip().upper() if body.callsign else None

    if body.delivery_mode == "confirmed":
        protocol_id = new_message_id()
        delivery_status = "transmitting"
        max_attempts = 3
    else:
        protocol_id = None
        delivery_status = None
        max_attempts = 1

    entry = TransmittedMessage(
        callsign=callsign,
        text=text,
        status="stored",
        delivery_mode=body.delivery_mode,
        protocol_id=protocol_id,
        protocol_version=ARQ_VERSION if body.delivery_mode == "confirmed" else None,
        delivery_status=delivery_status,
        attempts=0,
        max_attempts=max_attempts,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)

    return {
        "id": entry.id,
        "status": "stored",
        "protocol_id": protocol_id,
    }


# ---------------------------------------------------------------------------
# Rig control
# ---------------------------------------------------------------------------
@app.get("/api/rig")
async def api_get_rig() -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        context = await _radio_context(client)
        dial = context.get("dial")
        return {
            "dial": dial,
            "offset": context.get("offset"),
            "band": band_from_frequency(dial),
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/rig")
@app.post("/api/rig/frequency")
async def api_set_rig(body: FrequencyRequest) -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        await client.send("RIG.SET_FREQ", params={"DIAL": body.dial, "OFFSET": body.offset})
        return {"status": "ok", "dial": body.dial, "offset": body.offset}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Mode control
# ---------------------------------------------------------------------------
@app.get("/api/mode")
async def api_get_mode() -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        context = await _radio_context(client)
        speed = context.get("speed")
        return {
            "speed": speed,
            "mode": mode_from_speed(speed),
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/mode")
@app.post("/api/mode/speed")
async def api_set_mode(body: SpeedRequest) -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        await client.send("MODE.SET_SPEED", params={"SPEED": body.speed})
        return {"status": "ok", "speed": body.speed, "mode": mode_from_speed(body.speed)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Sent messages
# ---------------------------------------------------------------------------
@app.get("/api/sent")
async def api_sent_messages(
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    result = await session.scalars(
        select(TransmittedMessage)
        .where(TransmittedMessage.status.in_(("sent", "queued", "retrying")))
        .order_by(desc(TransmittedMessage.transmitted_at))
        .limit(limit)
    )
    return [
        {
            "id": msg.id,
            "callsign": msg.callsign,
            "text": msg.text,
            "status": msg.status,
            "delivery_mode": msg.delivery_mode,
            "protocol_id": msg.protocol_id,
            "delivery_status": msg.delivery_status,
            "attempts": msg.attempts,
            "max_attempts": msg.max_attempts,
            "transmitted_at": msg.transmitted_at.isoformat() if msg.transmitted_at else None,
            "confirmed_at": msg.confirmed_at.isoformat() if msg.confirmed_at else None,
        }
        for msg in result
    ]


# ---------------------------------------------------------------------------
# Frequency presets
# ---------------------------------------------------------------------------
@app.get("/api/frequencies")
@app.get("/api/js8/frequency-presets")
async def api_frequencies() -> list[dict[str, Any]]:
    return [
        {
            "band": p.band,
            "dial": p.dial,
            "label": p.label,
            "frequency_mhz": p.frequency_mhz,
        }
        for p in FREQUENCY_PRESETS
    ]


@app.get("/api/js8/offsets")
async def api_js8_offsets(
    band: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return {"band": band, "offsets": await available_offsets(session, band)}


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------
@app.get("/api/chats/stations")
async def api_chat_stations(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    stations = (await session.scalars(select(Station).order_by(desc(Station.last_seen)).limit(500))).all()
    return {
        "stations": [
            {
                "callsign": station.callsign,
                "name": station.name,
                "qth": station.qth,
                "notes": station.notes,
                "grid": station.grid,
                "last_seen": station.last_seen,
                "last_snr": station.last_snr,
                "last_offset": station.last_offset,
                "last_mode": station.last_mode,
                "js8link_capable": station.js8link_version is not None,
                "js8link_version": station.js8link_version,
            }
            for station in stations
        ]
    }


@app.get("/api/stations/{callsign:path}")
async def api_station_contact(
    callsign: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    normalized = callsign.strip().upper()
    station = await session.scalar(select(Station).where(Station.callsign == normalized))
    if station is None:
        raise HTTPException(status_code=404, detail="Station not found")
    return {
        "callsign": station.callsign,
        "name": station.name,
        "qth": station.qth,
        "notes": station.notes,
        "info_text": station.info_text,
        "info_updated_at": station.info_updated_at.isoformat() if station.info_updated_at else None,
        "status_text": station.status_text,
        "status_updated_at": station.status_updated_at.isoformat() if station.status_updated_at else None,
        "hearing_report": json.loads(station.hearing_report) if station.hearing_report else None,
        "hearing_updated_at": station.hearing_updated_at.isoformat() if station.hearing_updated_at else None,
        "grid_source": station.grid_source,
    }


@app.patch("/api/stations/{callsign:path}")
async def api_patch_station_contact(
    callsign: str,
    body: StationContactPatch,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    normalized = callsign.strip().upper()
    station = await session.scalar(select(Station).where(Station.callsign == normalized))
    if station is None:
        station = Station(callsign=normalized, message_count=0)
        session.add(station)
    station.name = body.name
    station.qth = body.qth
    station.notes = body.notes
    await session.commit()
    return {
        "callsign": station.callsign,
        "name": station.name,
        "qth": station.qth,
        "notes": station.notes,
    }


# ---------------------------------------------------------------------------
# Station Queries
# ---------------------------------------------------------------------------
@app.post("/api/stations/{callsign}/query")
async def api_station_query(
    callsign: str,
    body: StationQueryRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")

    # Find station
    result = await session.scalars(select(Station).where(Station.callsign == callsign.upper()))
    station = result.one_or_none()
    if station is None:
        raise HTTPException(status_code=404, detail=f"Station {callsign} not found")

    query_map = {
        "snr": "SNR?",
        "hearing": "HEARING?",
        "info": "INFO?",
        "grid": "GRID?",
        "status": "STATUS?",
    }
    query_suffix = query_map.get(body.query_type)
    if not query_suffix:
        raise HTTPException(status_code=400, detail=f"Invalid query type: {body.query_type}")

    query_text = f"{callsign.upper()} {query_suffix}"

    sq = StationQuery(
        station_id=station.id,
        query_type=body.query_type,
        status="pending",
    )
    session.add(sq)
    await session.flush()

    try:
        await transmit_js8_text(client, query_text, peer=callsign.upper())
        setattr(station, f"last_{body.query_type}_query_at", now())
        await session.commit()
        return {"status": "ok", "query_id": sq.id, "type": body.query_type}
    except Exception as exc:
        sq.status = "failed"
        sq.error_message = str(exc)
        await session.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/stations/{callsign}/queries")
async def api_station_queries(
    callsign: str,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    result = await session.scalars(select(Station).where(Station.callsign == callsign.upper()))
    station = result.one_or_none()
    if station is None:
        raise HTTPException(status_code=404, detail=f"Station {callsign} not found")

    queries = await session.scalars(
        select(StationQuery)
        .where(StationQuery.station_id == station.id)
        .order_by(desc(StationQuery.requested_at))
        .limit(50)
    )
    return [
        {
            "id": q.id,
            "type": q.query_type,
            "requested_at": q.requested_at.isoformat() if q.requested_at else None,
            "responded_at": q.responded_at.isoformat() if q.responded_at else None,
            "status": q.status,
            "snr_value": q.snr_value,
            "response_text": q.response_text,
            "error_message": q.error_message,
        }
        for q in queries
    ]


@app.get("/api/chats")
async def api_chats(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    received = (
        await session.scalars(
            select(ReceivedMessage)
            .where(
                ReceivedMessage.kind == "direct_message",
                ReceivedMessage.is_heartbeat.is_(False),
                ReceivedMessage.from_callsign.is_not(None),
                or_(
                    ReceivedMessage.to_callsign == local_callsign,
                    ReceivedMessage.to_callsign.is_(None),
                ),
            )
            .order_by(desc(ReceivedMessage.received_at))
            .limit(1000)
        )
    ).all()
    transmitted = (
        await session.scalars(
            select(TransmittedMessage)
            .where(
                TransmittedMessage.callsign.is_not(None),
                TransmittedMessage.is_heartbeat.is_(False),
            )
            .order_by(desc(TransmittedMessage.transmitted_at))
            .limit(1000)
        )
    ).all()
    read_states = {state.callsign: state for state in (await session.scalars(select(ChatReadState))).all()}
    latest: dict[str, dict[str, Any]] = {}
    unread: dict[str, int] = {}
    for message in received:
        to_callsign = str(message.to_callsign or "").upper()
        is_group_msg = to_callsign.startswith("@")
        # Group-addressed messages are keyed on the group, not the sender.
        callsign = to_callsign if is_group_msg else str(message.from_callsign).upper()
        timestamp = message.received_at
        if callsign not in latest or timestamp > latest[callsign]["last_message_at"]:
            latest[callsign] = {
                "callsign": callsign,
                "last_message": message.text,
                "last_message_at": timestamp,
                "last_direction": "rx",
            }
        read_state = read_states.get(callsign)
        last_read = read_state.last_read_at if read_state else None
        if last_read is None or timestamp > last_read:
            unread[callsign] = unread.get(callsign, 0) + 1
    for message in transmitted:
        callsign = str(message.callsign).upper()
        timestamp = message.transmitted_at
        if callsign not in latest or timestamp > latest[callsign]["last_message_at"]:
            latest[callsign] = {
                "callsign": callsign,
                "last_message": message.text,
                "last_message_at": timestamp,
                "last_direction": "tx",
            }

    station_rows = (
        (await session.scalars(select(Station).where(Station.callsign.in_(latest.keys())))).all() if latest else []
    )
    station_map = {station.callsign: station for station in station_rows}
    chats = []
    for callsign, summary in latest.items():
        station = station_map.get(callsign)
        read_state = read_states.get(callsign)
        chats.append(
            {
                **summary,
                "unread_count": unread.get(callsign, 0),
                "archived": bool(read_state and read_state.archived),
                "preferred_speed": read_state.preferred_speed if read_state else 0,
                "grid": station.grid if station else None,
                "last_heard_at": station.last_seen if station else None,
                "last_snr": station.last_snr if station else None,
                "last_offset": station.last_offset if station else None,
                "last_mode": station.last_mode if station else None,
                "js8link_capable": bool(station and station.js8link_version is not None),
                "js8link_version": station.js8link_version if station else None,
            }
        )
    chats.sort(key=lambda chat: chat["last_message_at"], reverse=True)
    config = await _get_app_config(session)
    return {"chats": chats, "selected_callsign": config.selected_chat_callsign}


@app.get("/api/chats/{callsign:path}/messages")
async def api_chat_messages(
    callsign: str,
    before: datetime | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    normalized = callsign.strip().upper()
    is_group_chat = normalized.startswith("@")
    if is_group_chat:
        # Group chat: match messages addressed TO the group.
        received_query = select(ReceivedMessage).where(
            ReceivedMessage.kind == "direct_message",
            ReceivedMessage.is_heartbeat.is_(False),
            ReceivedMessage.to_callsign == normalized,
        )
    else:
        # Direct chat: match messages FROM this callsign.
        received_query = select(ReceivedMessage).where(
            ReceivedMessage.kind == "direct_message",
            ReceivedMessage.is_heartbeat.is_(False),
            ReceivedMessage.from_callsign == normalized,
            or_(
                ReceivedMessage.to_callsign == local_callsign,
                ReceivedMessage.to_callsign.is_(None),
            ),
        )
    transmitted_query = select(TransmittedMessage).where(
        TransmittedMessage.callsign == normalized,
        TransmittedMessage.is_heartbeat.is_(False),
    )
    if before is not None:
        cutoff = utc_naive(before)
        received_query = received_query.where(ReceivedMessage.received_at < cutoff)
        transmitted_query = transmitted_query.where(TransmittedMessage.transmitted_at < cutoff)
    received = (await session.scalars(received_query.order_by(desc(ReceivedMessage.received_at)).limit(101))).all()
    transmitted = (
        await session.scalars(transmitted_query.order_by(desc(TransmittedMessage.transmitted_at)).limit(101))
    ).all()
    messages = [
        {
            "id": f"rx-{message.id}",
            "callsign": normalized,
            "from_callsign": message.from_callsign,
            "direction": "rx",
            "text": message.text,
            "timestamp": message.received_at,
            "status": "received",
            "band": message.band,
            "offset": message.offset,
            "mode": message.mode,
            "snr": message.snr,
            "grid": message.grid,
            "delivery_mode": message.delivery_mode,
            "protocol_id": message.protocol_id,
        }
        for message in received
    ] + [
        {
            "id": f"tx-{message.id}",
            "callsign": normalized,
            "from_callsign": None,
            "direction": "tx",
            "text": message.text,
            "timestamp": message.transmitted_at,
            "status": message.delivery_status or message.status,
            "band": message.band,
            "offset": message.offset,
            "mode": message.mode,
            "delivery_mode": message.delivery_mode,
            "delivery_status": message.delivery_status,
            "protocol_id": message.protocol_id,
            "attempts": message.attempts,
        }
        for message in transmitted
    ]
    messages.sort(key=lambda message: message["timestamp"])
    has_more = len(messages) > 100
    messages = messages[-100:]
    next_cursor = messages[0]["timestamp"].isoformat() if has_more and messages else None
    return {"messages": messages, "next_cursor": next_cursor}


@app.post("/api/chats/{callsign:path}/messages")
async def api_send_chat_message(
    callsign: str,
    body: MessageRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    payload = MessageRequest(
        callsign=callsign.strip().upper(),
        text=body.text,
        delivery_mode=body.delivery_mode,
    )
    return await api_send_message(payload, session)


@app.post("/api/chats/{callsign:path}/read")
async def api_mark_chat_read_alias(
    callsign: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    normalized = callsign.strip().upper()
    state = await session.scalar(select(ChatReadState).where(ChatReadState.callsign == normalized))
    timestamp = now()
    if state is None:
        state = ChatReadState(callsign=normalized, last_read_at=timestamp)
        session.add(state)
    else:
        state.last_read_at = timestamp
    await session.commit()
    return {"status": "ok", "callsign": normalized, "last_read_at": timestamp}


@app.patch("/api/chats/{callsign:path}/speed")
async def api_patch_chat_speed(
    callsign: str,
    body: ChatSpeedPatch,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    normalized = callsign.strip().upper()
    state = await session.scalar(select(ChatReadState).where(ChatReadState.callsign == normalized))
    if state is None:
        state = ChatReadState(callsign=normalized, preferred_speed=body.speed)
        session.add(state)
    else:
        state.preferred_speed = body.speed
    await session.commit()
    return {"status": "ok", "callsign": normalized, "preferred_speed": body.speed}


# ---------------------------------------------------------------------------
# Chat read state (legacy endpoints)
# ---------------------------------------------------------------------------
@app.get("/api/chat/read")
async def api_chat_read_state(
    session: AsyncSession = Depends(get_session),
) -> dict[str, str | None]:
    result = await session.scalars(select(ChatReadState))
    states = result.all()
    return {state.callsign: state.last_read_at.isoformat() if state.last_read_at else None for state in states}


@app.post("/api/chat/read/{callsign:path}")
async def api_mark_chat_read(
    callsign: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    result = await session.scalars(select(ChatReadState).where(ChatReadState.callsign == callsign.upper()))
    state = result.one_or_none()
    now_ts = now()
    if state is None:
        state = ChatReadState(callsign=callsign.upper(), last_read_at=now_ts)
        session.add(state)
    else:
        state.last_read_at = now_ts
    await session.commit()
    return {"status": "ok", "callsign": callsign.upper(), "last_read_at": now_ts.isoformat()}


@app.post("/api/chats/{callsign:path}/archive")
async def api_archive_chat(
    callsign: str,
    body: BoolToggleRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Archive or restore a conversation without changing radio history."""
    normalized = callsign.strip().upper()
    state = await session.scalar(select(ChatReadState).where(ChatReadState.callsign == normalized))
    if state is None:
        state = ChatReadState(callsign=normalized, archived=body.enabled)
        session.add(state)
    else:
        state.archived = body.enabled
    await session.commit()
    return {"status": "ok", "callsign": normalized, "archived": body.enabled}


# ---------------------------------------------------------------------------
# Unread counts
# ---------------------------------------------------------------------------
@app.get("/api/chat/unread")
async def api_chat_unread(
    session: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    states_result = await session.scalars(select(ChatReadState))
    states = {s.callsign: s.last_read_at for s in states_result}

    messages_result = await session.scalars(
        select(ReceivedMessage).where(
            ReceivedMessage.kind.in_(("direct_message", "directed_control")),
            ReceivedMessage.is_heartbeat.is_(False),
            ReceivedMessage.from_callsign.is_not(None),
        )
    )
    counts: dict[str, int] = {}
    for msg in messages_result:
        if not msg.from_callsign:
            continue
        callsign = msg.from_callsign.upper()
        last_read = states.get(callsign)
        msg_received = msg.received_at
        if last_read is None or (msg_received and msg_received > last_read):
            counts[callsign] = counts.get(callsign, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------
@app.websocket("/api/ws")
@app.websocket("/api/events")
async def api_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    connected_websockets.add(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
                await _record_diagnostic_trace(
                    source="websocket",
                    event_type="CLIENT.PING",
                    summary="WebSocket ping received",
                    interpretation="A web client sent a keepalive ping and JS8Link returned pong.",
                    raw_payload={"message": data},
                    processing=[
                        ("WebSocket input", "received", "The client message was received.", None),
                        ("WebSocket output", "sent", "The pong response was returned.", None),
                    ],
                )
            else:
                await _record_diagnostic_trace(
                    source="websocket",
                    event_type="CLIENT.MESSAGE",
                    summary="WebSocket message received",
                    interpretation="A web client sent a message that is not a supported JS8Link keepalive command.",
                    raw_payload={"message": data},
                    processing=[
                        (
                            "WebSocket input",
                            "received",
                            "The client message was received and ignored because no action is defined for it.",
                            None,
                        )
                    ],
                )
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket error")
    finally:
        connected_websockets.discard(websocket)


# ---------------------------------------------------------------------------
# Call selected
# ---------------------------------------------------------------------------
@app.get("/api/js8/call-selected", response_model=CallSelectedResponse)
async def api_get_call_selected() -> dict[str, Any]:
    """Read the JS8Call selection without making disconnects noisy for the UI poller."""
    if not client or not client.connected:
        return {"callsign": None}
    try:
        info = await client.request("RX.GET_CALL_SELECTED")
        callsign = str(info.get("value") or "").strip() or None
        return {"callsign": callsign}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/js8/call-selected/clear", response_model=CallSelectedResponse)
async def api_clear_call_selected() -> dict[str, Any]:
    """Attempt to clear JS8Call's selection and verify the result.

    JS8Call exposes ``RX.CALL_SELECTED`` as an outbound event, not as a
    documented setter. Some builds ignore an inbound event with an empty
    value, so never report success unless a follow-up GET confirms it.
    """
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        # RX.CALL_SELECTED is emitted by JS8Call when the UI selection changes.
        await client.send("RX.CALL_SELECTED", value="")
        selected = await client.request("RX.GET_CALL_SELECTED")
        callsign = str(selected.get("value") or "").strip() or None
        if callsign is not None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "JS8Call exposes no API command to clear the selected callsign; "
                    "the selection must be cleared in the JS8Call window."
                ),
            )
        return {"callsign": None}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.patch("/api/js8/call-selected", response_model=CallSelectedResponse)
async def api_set_call_selected(body: CallSelectedRequest) -> dict[str, Any]:
    """Select a callsign in JS8Call's call activity UI."""
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    callsign = body.callsign.strip().upper()
    try:
        selection_lock = transmit_locks.setdefault("__selection__", asyncio.Lock())
        async with selection_lock:
            await wait_for_tx_buffer_empty(client)
            await client.send("RX.CALL_SELECTED", value=callsign)
        return {"callsign": callsign}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# TX Text buffer
# ---------------------------------------------------------------------------
@app.get("/api/js8/tx-text", response_model=TxTextResponse)
async def api_get_tx_text() -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        info = await client.request("TX.GET_TEXT")
        return {"text": str(info.get("value") or "")}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/js8/tx-text")
async def api_set_tx_text(body: TxTextRequest) -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        await client.send("TX.SET_TEXT", value=body.text)
        return {"status": "ok", "text": body.text}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# JS8Call Inbox sync
# ---------------------------------------------------------------------------
@app.get("/api/js8/inbox")
async def api_get_inbox(
    callsign: str | None = Query(default=None),
) -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        params = {}
        if callsign:
            params["CALLSIGN"] = callsign
        info = await client.request("INBOX.GET_MESSAGES", params=params)
        messages = (info.get("params") or {}).get("MESSAGES", [])
        return {"messages": messages if isinstance(messages, list) else []}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/js8/inbox/store")
async def api_store_inbox(body: InboxStoreRequest) -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        info = await client.request(
            "INBOX.STORE_MESSAGE",
            params={"CALLSIGN": body.callsign, "TEXT": body.text},
        )
        message_id = (info.get("params") or {}).get("ID")
        return {"status": "ok", "id": message_id}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/js8/inbox/sync")
async def api_sync_inbox(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Sync JS8Call inbox messages into JS8Link's received_messages table."""
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        info = await client.request("INBOX.GET_MESSAGES")
        messages = (info.get("params") or {}).get("MESSAGES", [])
        if not isinstance(messages, list):
            messages = []
        synced = 0
        for msg in messages:
            msg_params = msg.get("params") or {}
            msg_text = msg_params.get("TEXT", "")
            msg_from = msg_params.get("FROM", "")
            if not msg_text or not msg_from:
                continue
            # Check if we already have this message
            existing = await session.scalar(
                select(ReceivedMessage).where(
                    ReceivedMessage.from_callsign == msg_from,
                    ReceivedMessage.text == msg_text,
                    ReceivedMessage.utc_timestamp
                    == utc_naive(
                        datetime.fromisoformat(msg_params["UTC"].replace(" ", "T"))
                        if msg_params.get("UTC")
                        else None
                    ),
                )
            )
            if existing is not None:
                continue
            entry = ReceivedMessage(
                callsign=msg_from,
                kind="direct_message",
                text=msg_text,
                delivery_mode="best_effort",
                message_type="RX.DIRECTED",
                from_callsign=msg_from,
                to_callsign=msg_params.get("TO"),
                utc_timestamp=(
                    utc_naive(
                        datetime.fromisoformat(msg_params["UTC"].replace(" ", "T"))
                        if msg_params.get("UTC")
                        else None
                    )
                ),
                raw_payload=str(msg),
            )
            session.add(entry)
            msg_to = str(msg_params.get("TO", "") or "").strip().upper()
            if not msg_to or msg_to.startswith("@") or (local_callsign and msg_to == local_callsign.upper()):
                entry.kind = "direct_message"
                await _restore_chat_on_activity(session, msg_from)
            else:
                entry.kind = "band_activity"
            synced += 1
        await session.commit()
        return {"status": "ok", "synced": synced}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# inbox_sync_scheduler
# ---------------------------------------------------------------------------
async def inbox_sync_scheduler() -> None:
    """Periodically sync JS8Call inbox with JS8Link database."""
    while True:
        await asyncio.sleep(300)  # every 5 minutes
        if not client or not client.connected:
            continue
        try:
            info = await client.request("INBOX.GET_MESSAGES")
            messages = (info.get("params") or {}).get("MESSAGES", [])
            if not isinstance(messages, list):
                continue
            async with SessionLocal() as session:
                synced = 0
                for msg in messages:
                    msg_params = msg.get("params") or {}
                    msg_text = msg_params.get("TEXT", "")
                    msg_from = msg_params.get("FROM", "")
                    if not msg_text or not msg_from:
                        continue
                    existing = await session.scalar(
                        select(ReceivedMessage)
                        .where(
                            ReceivedMessage.from_callsign == msg_from,
                            ReceivedMessage.text == msg_text,
                        )
                        .limit(1)
                    )
                    if existing is not None:
                        continue
                    entry = ReceivedMessage(
                        callsign=msg_from,
                        kind="direct_message",
                        text=msg_text,
                        delivery_mode="best_effort",
                        message_type="RX.DIRECTED",
                        from_callsign=msg_from,
                        to_callsign=msg_params.get("TO"),
                        utc_timestamp=(
                            utc_naive(
                                datetime.fromisoformat(msg_params["UTC"].replace(" ", "T"))
                                if msg_params.get("UTC")
                                else None
                            )
                        ),
                        raw_payload=str(msg),
                    )
                    session.add(entry)
                    msg_to = str(msg_params.get("TO", "") or "").strip().upper()
                    if not msg_to or msg_to.startswith("@") or (local_callsign and msg_to == local_callsign.upper()):
                        entry.kind = "direct_message"
                        await _restore_chat_on_activity(session, msg_from)
                    else:
                        entry.kind = "band_activity"
                    synced += 1
                if synced > 0:
                    await session.commit()
        except Exception:
            logger.exception("Inbox sync failed")


# ---------------------------------------------------------------------------
# Bandpass filter
# ---------------------------------------------------------------------------
@app.get("/api/js8/filter", response_model=FilterResponse)
async def api_get_filter() -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        info = await client.request("RX.GET_FILTER")
        params = info.get("params") or {}
        return {
            "center": params.get("CENTER"),
            "width": params.get("WIDTH"),
            "enabled": params.get("ENABLED"),
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.patch("/api/js8/filter")
async def api_patch_filter(body: FilterPatch) -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        send_params = {}
        if body.center is not None:
            send_params["CENTER"] = body.center
        if body.width is not None:
            send_params["WIDTH"] = body.width
        if send_params:
            await client.send("RX.SET_FILTER", params=send_params)
        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/js8/filter/enabled")
async def api_set_filter_enabled(body: FilterEnabledRequest) -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        await client.send("RX.SET_FILTER_ENABLED", value=str(body.enabled).lower())
        return {"status": "ok", "enabled": body.enabled}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Band activity snapshot
# ---------------------------------------------------------------------------
@app.get("/api/js8/band-activity", response_model=BandActivityResponse)
async def api_get_band_activity() -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        info = await _get_band_activity_snapshot()
        params = info.get("params") or {}
        offsets = []
        for key, value in params.items():
            if key == "_ID" or not isinstance(value, dict):
                continue
            offsets.append(
                {
                    "offset": value.get("OFFSET") or (int(key) if key.isdigit() else 0),
                    "dial": value.get("DIAL"),
                    "freq": value.get("FREQ"),
                    "snr": value.get("SNR"),
                    "text": value.get("TEXT", ""),
                    "utc": value.get("UTC"),
                    "band": band_from_frequency(value.get("DIAL")),
                }
            )
        offsets.sort(key=lambda o: o.get("snr") or -999, reverse=True)
        return {
            "offsets": offsets,
            "total_active": len(offsets),
            "timestamp": now(),
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# TX Queue status
# ---------------------------------------------------------------------------
@app.get("/api/js8/tx-queue", response_model=TxQueueResponse)
async def api_get_tx_queue(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")

    # Get queue depth from JS8Call
    queue_depth = 0
    try:
        queue_info = await client.request("TX.GET_QUEUE_DEPTH")
        queue_depth = (queue_info.get("params") or {}).get("DEPTH", 0)
    except Exception:
        pass

    # Get queued messages from our database
    queued = await session.scalars(
        select(TransmittedMessage)
        .where(TransmittedMessage.status == "queued")
        .order_by(TransmittedMessage.transmitted_at)
        .limit(20)
    )
    queued_list = [
        {
            "id": m.id,
            "callsign": m.callsign,
            "text": m.text,
            "status": m.status,
            "delivery_mode": m.delivery_mode,
            "protocol_id": m.protocol_id,
        }
        for m in queued
    ]

    # Get tx_state info (from event tracking)
    active = tx_state.get("active", False)
    current_message = tx_state.get("message", "")
    frames_sent = tx_state.get("frames_sent", 0)
    estimated = max(tx_state.get("estimated_frames", 1), 1)
    progress_pct = min(int(frames_sent / estimated * 100), 100)

    return {
        "active": active,
        "current_message": current_message or None,
        "frames_sent": frames_sent,
        "estimated_frames": estimated,
        "progress_pct": progress_pct,
        "queue_depth": queue_depth,
        "queued_messages": queued_list,
        "timestamp": now(),
    }


# ---------------------------------------------------------------------------
# Autoreply confirmation toggle
# ---------------------------------------------------------------------------
@app.post("/api/js8/autoreply-confirmation")
async def api_set_autoreply_confirmation(body: BoolToggleRequest) -> dict[str, Any]:
    if not client or not client.connected:
        raise HTTPException(status_code=503, detail="JS8Call not connected")
    try:
        await client.send("STATION.SET_AUTOREPLY_CONFIRMATION", value=str(body.enabled).lower())
        return {"status": "ok", "autoreply_confirmation": body.enabled}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# station_query_scheduler
# ---------------------------------------------------------------------------
async def station_query_scheduler() -> None:
    """Periodically poll stations for SNR, HEARING, INFO, GRID, and STATUS data."""
    while True:
        await asyncio.sleep(60)
        if not client or not client.connected:
            continue
        if tx_busy:
            continue
        # Respect JS8Call queue depth
        try:
            queue_info = await client.request("TX.GET_QUEUE_DEPTH")
            depth = (queue_info.get("params") or {}).get("DEPTH", 0)
            if depth > 2:
                continue
        except Exception:
            pass

        try:
            async with SessionLocal() as session:
                config = await _get_app_config(session)
                if not config.station_queries_enabled:
                    continue
                now_ts = now()

                # A missing reply must not keep the station in a permanent
                # pending state. Timed-out rows remain in the history, but no
                # longer block the next scheduled query for that station.
                timeout_cutoff = now_ts - timedelta(minutes=config.query_timeout_minutes)
                pending_queries = await session.scalars(
                    select(StationQuery).where(
                        StationQuery.status == "pending",
                        StationQuery.requested_at < timeout_cutoff,
                    )
                )
                for pending_query in pending_queries:
                    pending_query.status = "timeout"
                    pending_query.error_message = "No response within configured timeout"
                await session.flush()

                # Get the number of queries done this hour
                hour_ago = now_ts - timedelta(hours=1)
                query_count = await session.scalar(
                    select(func.count(StationQuery.id)).where(
                        StationQuery.requested_at >= hour_ago,
                    )
                )
                max_queries = config.query_max_per_hour
                remaining = max_queries - (query_count or 0)
                if remaining <= 0:
                    continue

                # Spread the hourly budget evenly across the hour. The
                # configured cooldown remains a minimum safety interval.
                last_query = await session.scalar(
                    select(StationQuery)
                    .where(StationQuery.status == "pending")
                    .order_by(desc(StationQuery.requested_at))
                    .limit(1)
                )
                if last_query is not None:
                    cooldown_remaining = (
                        query_spacing_seconds(
                            config.query_max_per_hour,
                            config.query_cooldown_seconds,
                        )
                        - (now_ts - last_query.requested_at).total_seconds()
                    )
                    if cooldown_remaining > 0:
                        continue

                # Ensure JS8Call connection is healthy before querying.
                if not client or not client.connected:
                    continue

                # Only query stations seen recently (active on the band).
                # A shorter window prevents querying stations that are no longer online.
                active_cutoff = now_ts - timedelta(minutes=15)
                stations = await session.scalars(
                    select(Station)
                    .where(
                        Station.last_seen >= active_cutoff,
                        Station.message_count > 0,
                    )
                    .order_by(desc(Station.last_seen))
                    .limit(50)
                )

                # Collect all (station, query_type) pairs that are due for querying.
                # We only send ONE query per cycle so they're naturally spread across
                # the hour instead of firing back-to-back.
                candidates: list[tuple[Station, str, str]] = []

                for station in stations:
                    # SNR: only query if we don't already have a recent value
                    # from a heartbeat.  Heartbeats update last_snr in _upsert_station.
                    snr_from_hb = station.last_snr is not None and station.last_snr_query_at is None
                    snr_stale = (
                        station.last_snr_query_at is not None
                        and (now_ts - station.last_snr_query_at).total_seconds()
                        >= config.query_interval_snr_minutes * 60
                    )
                    # Query SNR if never queried AND no heartbeat SNR, or if query
                    # interval has expired (even with heartbeat data, to refresh).
                    if (station.last_snr_query_at is None and not snr_from_hb) or snr_stale:
                        candidates.append((station, "snr", f"{station.callsign} SNR?"))
                        continue

                    # HEARING (second priority)
                    if (
                        not station.last_hearing_query_at
                        or (now_ts - station.last_hearing_query_at).total_seconds()
                        >= config.query_interval_hearing_minutes * 60
                    ):
                        candidates.append((station, "hearing", f"{station.callsign} HEARING?"))
                        continue

                    # STATUS (semi-static)
                    if (
                        not station.last_status_query_at
                        or (now_ts - station.last_status_query_at).total_seconds()
                        >= config.query_interval_status_hours * 3600
                    ):
                        candidates.append((station, "status", f"{station.callsign} STATUS?"))
                        continue

                    # INFO (static)
                    if (
                        not station.last_info_query_at
                        or (now_ts - station.last_info_query_at).total_seconds()
                        >= config.query_interval_info_days * 86400
                    ):
                        candidates.append((station, "info", f"{station.callsign} INFO?"))
                        continue

                    # GRID (static)
                    if (
                        not station.last_grid_query_at
                        or (now_ts - station.last_grid_query_at).total_seconds()
                        >= config.query_interval_grid_days * 86400
                    ):
                        candidates.append((station, "grid", f"{station.callsign} GRID?"))
                        continue

                if not candidates:
                    continue

                # Sort candidates: prefer most overdue SNR queries first, then by
                # signal strength (best SNR gets priority), then any other type.
                type_order = {"snr": 0, "hearing": 1, "status": 2, "info": 3, "grid": 4}
                ts = now_ts  # local alias for use in lambda
                candidates.sort(
                    key=lambda c: (
                        type_order.get(c[1], 99),
                        -(
                            (ts - getattr(c[0], f"last_{c[1]}_query_at")).total_seconds()
                            if getattr(c[0], f"last_{c[1]}_query_at", None) is not None
                            else float("inf")
                        ),
                        -(c[0].last_snr or -999),
                    )
                )

                # Send only the single highest-priority query this cycle.
                # The cooldown mechanism ensures the next one waits its turn.
                station_obj, query_type, query_value = candidates[0]

                # Record the query
                sq = StationQuery(
                    station_id=station_obj.id,
                    query_type=query_type,
                    status="pending",
                )
                session.add(sq)
                await session.flush()
                try:
                    await transmit_js8_text(
                        client,
                        query_value,
                        peer=station_obj.callsign,
                    )
                    setattr(station_obj, f"last_{query_type}_query_at", now_ts)
                    await session.commit()
                except Exception:
                    sq.status = "failed"
                    sq.error_message = "TX send failed"
                    await session.commit()
        except Exception:
            logger.exception("Station query scheduler failed")


# ---------------------------------------------------------------------------
# Startup / Shutdown
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def on_startup() -> None:
    global client

    # Load config and connect
    async with SessionLocal() as session:
        await _repair_legacy_local_timestamps(session)
        await _repair_legacy_monitor_records(session)
        config = await _get_app_config(session)
        host, port = config.js8_host, config.js8_port

    client = JS8CallClient(
        host=host,
        port=port,
        on_event=on_js8_event,
        on_message=on_js8_api_message,
        on_outbound=on_js8_api_outbound,
        on_malformed=on_js8_api_malformed,
    )
    try:
        await connect_client(host, port, client)
        logger.info("Connected to JS8Call at %s:%s, callsign=%s", host, port, local_callsign)
    except Exception:
        logger.warning("Could not connect to JS8Call at %s:%s on startup", host, port)

    # Start background tasks
    asyncio.create_task(connection_monitor())
    asyncio.create_task(offset_optimizer())
    asyncio.create_task(cleanup_received_messages())
    asyncio.create_task(arq_retry_scheduler())
    asyncio.create_task(inbox_sync_scheduler())
    asyncio.create_task(station_query_scheduler())


@app.on_event("shutdown")
async def on_shutdown() -> None:
    if client:
        await client.close()


# ---------------------------------------------------------------------------
# Frontend serving
# ---------------------------------------------------------------------------
# Keep these catch-all routes after every API route.  FastAPI matches routes in
# registration order; registering the SPA fallback earlier would turn valid
# API paths into 404 responses whenever a production frontend is present.
frontend_dist = settings.frontend_dist

if frontend_dist.exists() and (frontend_dist / "index.html").exists():

    @app.get("/assets/{rest_of_path:path}")
    async def assets_proxy(rest_of_path: str) -> FileResponse:
        file_path = frontend_dist / "assets" / rest_of_path
        if not file_path.exists():
            raise HTTPException(status_code=404)
        return FileResponse(file_path)

    @app.get("/help/{rest_of_path:path}")
    async def help_assets_proxy(rest_of_path: str) -> FileResponse:
        file_path = frontend_dist / "help" / rest_of_path
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(file_path)

    @app.get("/{rest_of_path:path}")
    async def frontend_fallback(rest_of_path: str) -> HTMLResponse:
        first_segment = rest_of_path.split("/")[0] if rest_of_path else ""
        if first_segment in ("api", "ws", "assets", "help"):
            raise HTTPException(status_code=404)
        index_path = frontend_dist / "index.html"
        return HTMLResponse(index_path.read_text(encoding="utf-8"))

    @app.get("/")
    async def frontend_root() -> HTMLResponse:
        index_path = frontend_dist / "index.html"
        return HTMLResponse(index_path.read_text(encoding="utf-8"))
