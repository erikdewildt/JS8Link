# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
import re
from datetime import UTC, datetime
from typing import Any

from .js8_protocol import parse_heartbeat_report

_SENDER_PREFIX = re.compile(
    r"^\s*(?P<sender>(?=[A-Z0-9/]*[A-Z])(?=[A-Z0-9/]*\d)[A-Z0-9/]{3,16}):\s*(?P<text>.*?)(?:\s*♢\s*)?$",
    re.IGNORECASE,
)
_ACTIVITY_CALLSIGN = re.compile(
    r"^(?P<sender>(?=[A-Z0-9/]*[A-Z])(?=[A-Z0-9/]*\d)[A-Z0-9/]{3,16})\s+(?P<text>.+)$",
    re.IGNORECASE,
)

DIRECTED_CONTROL_COMMANDS = {
    "ACK",
    "GRID",
    "HEARING",
    "HEARTBEAT",
    "INFO",
    "QUERY",
    "SNR",
    "STATUS",
}


def extract_sender_and_text(value: object) -> tuple[str | None, str]:
    """Extract JS8Call's displayed ``CALLSIGN: payload`` prefix."""
    text = str(value or "").strip()
    match = _SENDER_PREFIX.match(text)
    if not match:
        return None, text
    return match.group("sender").upper(), match.group("text").strip()


def extract_activity_sender_and_text(value: object) -> tuple[str | None, str]:
    """Extract a sender from JS8Call activity in either supported display form.

    Directed traffic is commonly displayed as ``CALLSIGN: text`` while the
    band-activity snapshot uses ``CALLSIGN text``.  The second form is only
    accepted when the first token has the shape of a callsign, so ordinary
    activity such as ``CQ N0CALL`` is not incorrectly attributed.
    """
    sender, text = extract_sender_and_text(value)
    if sender:
        return sender, text
    raw = str(value or "").strip()
    match = _ACTIVITY_CALLSIGN.match(raw)
    if not match:
        return None, raw
    return match.group("sender").upper(), match.group("text").strip().rstrip("♢").rstrip()


def normalize_monitor_text(value: object) -> str:
    """Normalize JS8Call display-only suffixes for monitor deduplication."""
    return re.sub(r"\s*♢\s*$", "", str(value or "").strip())


def heartbeat_frame_text(sender: str | None, target: str | None, body: object) -> str:
    """Return one canonical text representation for a heartbeat frame."""
    payload = normalize_monitor_text(body)
    if sender and target and payload.upper().startswith(f"{target.upper()} "):
        return f"{sender.upper()} {payload}"
    return payload


def is_heartbeat(message: dict[str, Any]) -> bool:
    if message.get("type", "").upper() != "RX.DIRECTED":
        return False
    command = str((message.get("params") or {}).get("CMD", "")).strip().upper()
    if command == "HEARTBEAT":
        return True
    # JS8Call-improved can expose a heartbeat response as CMD=MSG. In that
    # form the protocol marker is only present in the displayed value.
    value = str(message.get("value") or "")
    return re.search(r"\bHEARTBEAT(?:\s+SNR\s+-?\d+)?\b", value, re.IGNORECASE) is not None


def classify_received_traffic(
    message_type: str | None,
    command: str | None = None,
    heartbeat: bool = False,
) -> str:
    """Classify an incoming JS8 event for user-facing message and monitor views."""
    event = (message_type or "").lower()
    normalized_command = (command or "").strip().upper()
    if heartbeat or normalized_command == "HEARTBEAT":
        return "heartbeat"
    if event in {"rx.activity", "rx.band_activity"}:
        return "band_activity"
    if event == "rx.directed":
        if normalized_command in DIRECTED_CONTROL_COMMANDS:
            return "directed_control"
        return "direct_message"
    return "unknown"


def event_timestamp(message: dict[str, Any]) -> datetime:
    raw = (message.get("params") or {}).get("UTC")
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(raw / 1000, tz=UTC)
    if isinstance(raw, str):
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            pass
    return datetime.now(UTC)


def parse_heartbeat_activity(message: dict[str, Any]) -> tuple[str, str, int | None] | None:
    """Parse JS8Call activity text for heartbeat *reception reports*.

    Handles the report form:
    - ``CALLSIGN: TARGET HEARTBEAT SNR -12``

    A group beacon such as ``CALLSIGN: @HB HEARTBEAT IO93`` is deliberately
    excluded: it announces the sender and requests acknowledgements; it is
    not an SNR report about a station named ``@HB``.
    """
    if message.get("type", "").upper() not in {"RX.ACTIVITY", "RX.BAND_ACTIVITY"}:
        return None
    meaning = parse_heartbeat_report(message.get("value", ""), message.get("params") or {})
    if meaning is None or meaning.source is None or meaning.target is None:
        return None
    return meaning.source, meaning.target, meaning.snr


_DIRECTED_ACTIVITY = re.compile(
    r"^(?P<source>[A-Z0-9/]{3,16}):\s+(?P<target>[A-Z0-9/]{3,16})\s+",
    re.IGNORECASE,
)


def parse_activity_sender_target(raw: str) -> tuple[str, str, str] | None:
    """Extract source, target, and remainder from band-activity text.

    JS8Call's band-activity snapshot shows traffic as
    ``SOURCE: TARGET payload`` or ``SOURCE: payload``.  When both a source
    and a target callsign are present we can build a station link from
    passively observed traffic — no active query needed.
    """
    match = _DIRECTED_ACTIVITY.match(raw.strip())
    if not match:
        return None
    source = match.group("source").upper()
    target = match.group("target").upper()
    if source == target:
        return None
    return source, target, raw[match.end():].strip()
