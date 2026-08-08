# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
"""Semantic interpretation of JS8Call API envelopes and on-air text.

This module is deliberately independent from persistence and UI code.  It is
the single place where JS8Call wire data is translated into operator-readable
meaning, so diagnostics and data processing cannot silently develop different
protocol interpretations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .modes import mode_from_speed

_CALL = r"[A-Z0-9/]{3,16}"
_SOURCE_PREFIX = re.compile(rf"^\s*(?P<source>{_CALL}):\s*(?P<body>.*?)\s*$", re.IGNORECASE)
_DIRECTED_BODY = re.compile(r"^(?P<target>@?[A-Z0-9/]+)(?:\s+(?P<body>.*))?$", re.IGNORECASE)
_GRID = re.compile(r"^[A-R]{2}[0-9]{2}(?:[A-X]{2})?(?:[0-9]{2})?(?:[A-X]{2})?$", re.IGNORECASE)
_SNR = re.compile(r"^[+-]?\d{1,2}$")
_RELAY = re.compile(
    r"^(?P<path>(?:@?[A-Z0-9/]*>)+)\s*(?P<payload>.*)$", re.IGNORECASE
)


@dataclass(frozen=True, slots=True)
class AirMessageMeaning:
    """Structured meaning of one decoded or transmitted JS8 text message."""

    kind: str
    source: str | None
    target: str | None
    command: str | None
    payload: str
    summary: str
    interpretation: str
    snr: int | None = None
    grid: str | None = None
    message_id: str | None = None
    relay_path: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class APIMessageMeaning:
    """Operator-readable meaning of one JS8Call JSON API envelope."""

    summary: str
    interpretation: str
    air_message: AirMessageMeaning | None = None


def _clean_text(value: object) -> str:
    return re.sub(r"\s*♢\s*$", "", str(value or "").strip()).strip()


def _format_snr(value: object) -> str:
    try:
        return f"{int(str(value)):+03d}"
    except (TypeError, ValueError):
        return str(value)


def _source_and_body(value: object, params: dict[str, Any]) -> tuple[str | None, str]:
    text = _clean_text(value)
    # Protocol says structured params take precedence over the displayed value.
    source = str(params.get("FROM") or params.get("CALL") or "").strip().upper() or None
    if source:
        # Drop the CALLSIGN: prefix from the body when we used params.FROM.
        match = _SOURCE_PREFIX.match(text)
        body = match.group("body").strip() if match else text
        return source, body
    # Fall back to the displayed value for sources without structured params
    # (common in RX.ACTIVITY and RX.BAND_ACTIVITY snapshots).
    match = _SOURCE_PREFIX.match(text)
    if match:
        return match.group("source").upper(), match.group("body").strip()
    return None, text


def _target_and_body(body: str, params: dict[str, Any]) -> tuple[str | None, str]:
    target = str(params.get("TO") or "").strip().upper() or None
    match = _DIRECTED_BODY.match(body)
    if match:
        text_target = match.group("target").upper()
        matched_body = (match.group("body") or "").strip()
        if target is None or text_target == target:
            return text_target, matched_body
    return target, body


def _meaning(
    kind: str,
    source: str | None,
    target: str | None,
    command: str | None,
    payload: str,
    summary: str,
    interpretation: str,
    *,
    snr: int | None = None,
    grid: str | None = None,
    message_id: str | None = None,
    relay_path: tuple[str, ...] = (),
) -> AirMessageMeaning:
    return AirMessageMeaning(
        kind=kind,
        source=source,
        target=target,
        command=command,
        payload=payload,
        summary=summary,
        interpretation=interpretation,
        snr=snr,
        grid=grid,
        message_id=message_id,
        relay_path=relay_path,
    )


def interpret_air_message(value: object, params: dict[str, Any] | None = None) -> AirMessageMeaning:
    """Interpret documented JS8Call directed commands and common text frames.

    ``params`` takes precedence where JS8Call has already decoded structured
    fields, while the displayed value remains the fallback for RX.ACTIVITY and
    RX.BAND_ACTIVITY snapshots.
    """

    params = params or {}
    source, prefixed_body = _source_and_body(value, params)
    target, body = _target_and_body(prefixed_body, params)
    command = str(params.get("CMD") or "").strip().upper() or None
    body_upper = body.upper().strip()

    # A heartbeat beacon is addressed to the special @HB group and carries
    # the sender's grid.  It is an announcement/invitation for ACK reception
    # reports, never a statement that the sender received a station named @HB.
    if target == "@HB" and (command == "HEARTBEAT" or body_upper.startswith("HEARTBEAT")):
        remainder = re.sub(r"^HEARTBEAT\b", "", body_upper).strip()
        param_grid = str(params.get("GRID") or "").strip().upper()
        grid = param_grid or (remainder.split()[0] if remainder and _GRID.match(remainder.split()[0]) else None)
        station = source or "A station"
        grid_text = f" from locator {grid}" if grid else ""
        return _meaning(
            "heartbeat_beacon",
            source,
            target,
            "HEARTBEAT",
            remainder,
            "Heartbeat beacon received",
            f"{station} broadcast a heartbeat{grid_text} to the @HB heartbeat group. "
            "This announces that the station is active and invites enabled stations that hear it "
            "to return a lightweight heartbeat acknowledgement/reception report.",
            grid=grid,
        )

    heartbeat = re.match(
        r"^HEARTBEAT\s+SNR\s+(?P<snr>[+-]?\d{1,2})(?:\s+MSG\s+(?P<id>\d+))?(?:\s+(?P<extra>.*))?$",
        body_upper,
    )
    if target and heartbeat:
        snr = int(heartbeat.group("snr"))
        message_id = heartbeat.group("id")
        station = source or "A station"
        stored = f" It also advertises stored message {message_id}." if message_id else ""
        return _meaning(
            "heartbeat_report",
            source,
            target,
            "HEARTBEAT SNR",
            body,
            "Heartbeat reception report received",
            f"{station} reports that it received {target}'s heartbeat at {snr:+03d} dB.{stored}",
            snr=snr,
            message_id=message_id,
        )

    # Partial heartbeat: SNR value missing or corrupted, but the frame is clearly
    # a reception report.  Record it without an SNR so the link is still created.
    if target and body_upper.startswith("HEARTBEAT"):
        station = source or "A station"
        return _meaning(
            "heartbeat_report",
            source,
            target,
            "HEARTBEAT",
            body,
            "Partial heartbeat reception report received",
            f"{station} reports that it received {target}'s heartbeat, but the SNR value was not decodable.",
            snr=None,
        )

    # Queries which request an automatic response when AUTO is enabled.
    query_names = {
        "SNR?": "its received signal report for the sender",
        "GRID?": "its grid locator",
        "INFO?": "its station information",
        "STATUS?": "its station status",
        "HEARING?": "the stations it currently hears",
        "AGN?": "a repeat of its previous transmission",
        "QSL?": "confirmation of the preceding transmission",
        "HW CPY?": "a reception report",
    }
    candidate = command or body_upper
    for query, requested in query_names.items():
        if candidate == query or body_upper.startswith(f"{query} "):
            station = source or "A station"
            destination = target or "the addressed station"
            return _meaning(
                "directed_query",
                source,
                target,
                query,
                body,
                "Directed query received",
                f"{station} asks {destination} to return {requested}. "
                "JS8Call may answer automatically when AUTO is enabled.",
            )

    query_match = re.match(r"^QUERY\s+(?P<query>CALL|MSGS|MSG)(?:\s+(?P<argument>.+?))?\??$", body_upper)
    if query_match:
        query_type = query_match.group("query")
        argument = (query_match.group("argument") or "").strip()
        descriptions = {
            "CALL": f"whether it can communicate directly with {argument or 'the requested station'}",
            "MSGS": "which stored messages are waiting for the sender",
            "MSG": f"stored message {argument or '(missing id)'}",
        }
        return _meaning(
            "stored_message_query" if query_type.startswith("MSG") else "reachability_query",
            source,
            target,
            f"QUERY {query_type}",
            argument,
            "JS8 network query received",
            f"{source or 'A station'} asks {target or 'the addressed station'} for {descriptions[query_type]}.",
            message_id=argument if query_type == "MSG" and argument else None,
        )

    # Directed responses and reports.
    response_patterns: tuple[tuple[str, str], ...] = (
        ("SNR", "signal_report"),
        ("GRID", "grid_report"),
        ("INFO", "info_report"),
        ("STATUS", "status_report"),
        ("HEARING", "hearing_report"),
    )
    for response_command, kind in response_patterns:
        match = re.match(rf"^{response_command}(?:\s+(?P<payload>.*))?$", body, re.IGNORECASE)
        if command == response_command and not match:
            match = re.match(r"^(?P<payload>.*)$", body)
        if not match:
            continue
        payload = (match.groupdict().get("payload") or "").strip()
        if response_command == "SNR":
            if _SNR.match(payload):
                snr = int(payload)
                explanation = (
                    f"{source or 'A station'} reports receiving {target or 'the addressed station'} at {snr:+03d} dB."
                )
                return _meaning(
                    kind, source, target, response_command, payload, "Signal report received", explanation, snr=snr
                )
            continue  # SNR response with non-numeric payload — skip
        if response_command == "GRID":
            if payload:
                grid = payload.split()[0].upper()
                return _meaning(
                    kind,
                    source,
                    target,
                    response_command,
                    payload,
                    "Grid report received",
                    f"{source or 'A station'} reports grid locator {grid}.",
                    grid=grid,
                )
            continue  # GRID response with empty payload — skip
        if payload:
            label = {"INFO": "station information", "STATUS": "station status", "HEARING": "heard-station list"}[
                response_command
            ]
            return _meaning(
                kind,
                source,
                target,
                response_command,
                payload,
                f"{label.title()} received",
                f"{source or 'A station'} returned {label} to {target or 'the addressed station'}: {payload}",
            )

    msg_to = re.match(r"^MSG\s+TO:\s*(?P<recipient>\S+)\s+(?P<text>.+)$", body, re.IGNORECASE)
    if msg_to:
        recipient = msg_to.group("recipient").upper()
        return _meaning(
            "stored_message",
            source,
            target,
            "MSG TO:",
            msg_to.group("text"),
            "Store-and-forward message received",
            f"{source or 'A station'} asks {target or 'the addressed station'} to store a message for {recipient}.",
        )

    msg = re.match(r"^MSG(?:\s+(?P<text>.*))?$", body, re.IGNORECASE)
    if command == "MSG" or msg:
        text = (msg.group("text") if msg else body) or ""
        return _meaning(
            "inbox_message",
            source,
            target,
            "MSG",
            text.strip(),
            "Inbox message received",
            f"{source or 'A station'} asks {target or 'the addressed station'} "
            f"to store and display an inbox message: {text.strip()}",
        )

    # Relay messages: CALL1>CALL2>MESSAGE or CALL>MESSAGE
    relay_match = _RELAY.match(body)
    if relay_match and target:
        path_str = relay_match.group("path")
        payload = relay_match.group("payload")
        hops = tuple(h.strip(">") for h in path_str.split(">") if h.strip(">"))
        return _meaning(
            "relay_message",
            source,
            target,
            ">",
            body,
            "Relay message received",
            f"{source or 'A station'} sent a relayed message through {len(hops)} hop(s): "
            f"{' > '.join(hops)}. Payload: {payload}",
            relay_path=hops,
        )

    short = next(
        (
            token
            for token in ("ACK", "QSL", "YES", "NO", "RR", "FB", "TU", "73", "SK", "DIT DIT")
            if body_upper == token
        ),
        None,
    )
    if short:
        return _meaning(
            "short_response",
            source,
            target,
            short,
            body,
            "Directed acknowledgement received",
            f"{source or 'A station'} sent the documented JS8 short response {short} "
            f"to {target or 'the addressed station'}.",
        )

    # Partial short responses: JS8Call sometimes decodes "R" for "RR",
    # "7" for "73", or single characters from a corrupted frame.
    partial_short: dict[str, str] = {"R": "RR", "7": "73", "SK": "SK"}
    if body_upper in partial_short and target:
        intended = partial_short[body_upper]
        return _meaning(
            "short_response",
            source,
            target,
            intended,
            body,
            "Partial acknowledgement received",
            f"{source or 'A station'} sent what appears to be a partial {intended} "
            f"to {target or 'the addressed station'} (decoded as '{body_upper}').",
        )

    if (
        re.match(r"^CQ(?:\s|$)", body_upper)
        or body_upper == "CQ"
        or target == "CQ"
        or (target == "@ALLCALL" and "CQ" in body_upper)
    ):
        # When the body or target is "CQ" this is a CQ call, not a directed
        # message to a station named "CQ" (which is not a valid callsign).
        if target == "CQ" and source:
            target = None  # Don't report CQ as the target station.
        grid = next((part for part in body_upper.split() if _GRID.match(part)), None)
        return _meaning(
            "cq",
            source if source else target if target and target != "CQ" else None,
            None,
            "CQ",
            body,
            "CQ call received",
            f"{source or 'A station'} is calling CQ{f' from locator {grid}' if grid else ''}.",
            grid=grid,
        )

    if source or target:
        return _meaning(
            "directed_message",
            source,
            target,
            command,
            body,
            "Directed message received",
            f"{source or 'A station'} sent a directed message to {target or 'an unspecified destination'}: {body}",
        )
    return _meaning(
        "free_text",
        None,
        None,
        command,
        body,
        "Undirected traffic received",
        f"JS8Call decoded free text without a reliably identified sender or destination: {body or '(empty frame)'}",
    )


def describe_api_message(
    message: dict[str, Any], *, is_response: bool = False, outbound: bool = False
) -> APIMessageMeaning:
    """Describe every documented JS8Call-improved API 3.x message type."""

    message_type = str(message.get("type") or "UNKNOWN").upper()
    raw_params = message.get("params")
    params: dict[str, Any] = raw_params if isinstance(raw_params, dict) else {}
    value = message.get("value") or ""

    if message_type in {"RX.ACTIVITY", "RX.DIRECTED"}:
        air = interpret_air_message(value, params)
        local_snr = params.get("SNR")
        interpretation = air.interpretation
        if local_snr is not None and air.source:
            interpretation += (
                f" This JS8Call instance decoded {air.source}'s transmitted frame at "
                f"{_format_snr(local_snr)} dB; that local receive measurement is distinct "
                "from any SNR written inside the message."
            )
        return APIMessageMeaning(air.summary, interpretation, air)

    if message_type == "RX.BAND_ACTIVITY":
        count = sum(1 for key, item in params.items() if not str(key).startswith("_") and isinstance(item, dict))
        return APIMessageMeaning(
            "Band activity snapshot received",
            f"JS8Call returned {count} current band-activity entries. Each entry must be "
            "interpreted independently from its TEXT and receive metadata, checked for age "
            "and deduplicated before storage.",
        )

    if message_type == "RX.SPOT":
        call = str(params.get("CALL") or "an unknown station")
        return APIMessageMeaning(
            "Station spot received",
            f"JS8Call spotted {call} at {params.get('SNR', 'unknown')} dB with grid "
            f"{params.get('GRID') or 'unknown'}, dial {params.get('DIAL') or 'unknown'} Hz "
            f"and offset {params.get('OFFSET') or 'unknown'} Hz.",
        )

    if message_type == "TX.FRAME":
        air = interpret_air_message(value, params) if str(value).strip() else None
        return APIMessageMeaning(
            "Radio frame transmitted",
            air.interpretation
            if air
            else f"JS8Call emitted one encoded TX frame containing {len(params.get('TONES') or [])} tone symbols.",
            air,
        )

    if message_type in {"RIG.PTT", "RIG.PTT_STATUS"}:
        active = bool(params.get("PTT"))
        return APIMessageMeaning(
            "Transmitter keyed" if active else "Transmitter released",
            "JS8Call reports that PTT is active and RF transmission is in progress."
            if active
            else "JS8Call reports that PTT is inactive and the radio has returned to receive.",
        )

    # ── Response types — JS8Call returns these in response to GET requests ──
    response_descriptions = {
        "RIG.FREQ": f"Dial {params.get('DIAL')} Hz, offset {params.get('OFFSET')} Hz.",
        "MODE.SPEED": f"Speed code {params.get('SPEED')} ({mode_from_speed(params.get('SPEED')) or 'unknown'}).",
        "STATION.CALLSIGN": f"Callsign {value or params.get('CALLSIGN') or 'unknown'}.",
        "STATION.GRID": f"Grid locator {value or params.get('GRID') or 'unknown'}.",
        "STATION.INFO": f"Station information: {value or '(empty)'}.",
        "STATION.STATUS": f"Station status: {value or '(empty)'}.",
        "STATION.SPOT": f"Spot reporting is {'enabled' if str(value).lower() == 'true' else 'disabled'}.",
        "STATION.CONFIG": (
            f"JS8Call configuration: auto_reply={params.get('AUTO_REPLY')}, "
            f"hb_interval={params.get('HB_INTERVAL')}, groups={len(params.get('GROUPS') or [])}."
        ),
        "STATION.VERSION": f"JS8Call version {value or params.get('VERSION') or 'unknown'}.",
        "STATION.OS": (
            f"Host OS: {params.get('OS_NAME') or 'unknown'} "
            f"(kernel {params.get('OS_KERNEL') or 'unknown'} "
            f"{params.get('OS_KERNEL_VERSION') or ''})".strip()
        ),
        "RX.FREE_OFFSETS": (
            f"{len([k for k in params if not str(k).startswith('_')])} free passband "
            f"segments reported."
        ),
        "RX.CALL_SELECTED": f"Selected callsign: {value or params.get('CALLSIGN') or 'none'}.",
        "RX.CALL_ACTIVITY": (
            f"{len([k for k in params if not str(k).startswith('_') and isinstance(params.get(k), dict)])} "
            f"heard stations reported."
        ),
        "RX.TEXT": f"Receive window text: {value or '(empty)'}.",
        "RX.BAND_ACTIVITY": (
            f"{sum(1 for k, v in params.items() if not str(k).startswith('_') and isinstance(v, dict))} "
            f"band-activity entries."
        ),
        "TX.TEXT": f"Transmit buffer text: {value or '(empty)'}.",
        "TX.QUEUE_DEPTH": f"{params.get('DEPTH', 0)} messages in the transmit queue.",
        "TX.FRAME": f"Transmitted frame encoded in {len(params.get('TONES') or [])} tones.",
        "INBOX.MESSAGES": f"{len(params.get('MESSAGES') or [])} inbox messages.",
        "INBOX.MESSAGE": f"Inbox message stored with id {params.get('ID') or 'unknown'}.",
        "RIG.PTT_STATUS": (
            "PTT is active and RF transmission is in progress."
            if params.get("PTT")
            else "PTT is inactive and the radio has returned to receive."
        ),
    }
    response_detail = response_descriptions.get(message_type)
    if response_detail:
        direction = "JS8Call returned this data" if is_response else "JS8Call emitted this data"
        return APIMessageMeaning(f"{message_type} received", f"{direction}. {response_detail}")

    descriptions = {
        "PING": "Wake the JS8Call API connection.",
        "RIG.GET_FREQ": "Request the current radio dial frequency and audio offset.",
        "RIG.SET_FREQ": f"Set dial frequency to {params.get('DIAL')} Hz and offset to {params.get('OFFSET')} Hz.",
        "RIG.GET_PTT": "Request the current transmitter PTT state.",
        "RIG.SET_TUNE": f"Turn tuning {'on' if str(value).lower() == 'true' else 'off'}.",
        "RIG.TX_HALT": "Stop the transmitter immediately.",
        "STATION.GET_CALLSIGN": "Request the configured station callsign.",
        "STATION.GET_GRID": "Request the configured station grid locator.",
        "STATION.SET_GRID": f"Set the station grid locator to {value}.",
        "STATION.GET_INFO": "Request the station information text.",
        "STATION.SET_INFO": "Update the station information text.",
        "STATION.GET_STATUS": "Request the station status text.",
        "STATION.SET_STATUS": "Update the station status text.",
        "STATION.VERSION": "Request or report the JS8Call version and API compatibility.",
        "STATION.GET_OS": "Request or report JS8Call host operating-system information.",
        "STATION.GET_SPOT": "Request whether JS8Call spot reporting is enabled.",
        "STATION.SET_SPOT": f"Set JS8Call spot reporting to {value}.",
        "RX.GET_CALL_ACTIVITY": "Request the recent heard-station list.",
        "RX.GET_CALL_SELECTED": "Request the callsign currently selected in the JS8Call UI.",
        "RX.GET_BAND_ACTIVITY": "Request the current per-offset band-activity snapshot.",
        "RX.GET_TEXT": "Request the directed-message receive window text.",
        "RX.GET_FREE_OFFSETS": "Request free passband segments for the requested mode and frequency bounds.",
        "TX.GET_TEXT": "Request the current editable transmit buffer.",
        "TX.SET_TEXT": "Replace the editable transmit buffer without starting transmission.",
        "TX.SEND_MESSAGE": f"Queue text for transmission in the next transmit cycle: {value}",
        "TX.GET_QUEUE_DEPTH": "Request the number of messages left in the transmit queue.",
        "MODE.GET_SPEED": "Request the current JS8 transmit speed.",
        "MODE.SET_SPEED": f"Set the JS8 transmit speed code to {params.get('SPEED')}.",
        "INBOX.GET_MESSAGES": "Request all messages stored in the local JS8Call inbox.",
        "INBOX.STORE_MESSAGE": (
            f"Store a local inbox message for {params.get('CALLSIGN') or 'an unspecified callsign'}."
        ),
        "WINDOW.RAISE": "Bring the JS8Call application window to the foreground.",
        "STATION.CLOSING": f"JS8Call is closing: {params.get('REASON') or 'no reason supplied'}.",
        "API.ERROR": f"JS8Call rejected or could not parse an API request: {value}.",
    }
    detail = descriptions.get(message_type)
    if detail:
        direction = "JS8Link sent this command to JS8Call" if outbound else "JS8Call returned or emitted this data"
        return APIMessageMeaning(f"{message_type} {'sent' if outbound else 'received'}", f"{direction}. {detail}")
    direction = "sent to" if outbound else "received from"
    response = " as a correlated response" if is_response else ""
    return APIMessageMeaning(
        "Undocumented JS8Call API message",
        f"{message_type} was {direction} JS8Call{response}. JS8Link preserves the complete "
        "envelope because this type is not documented by the API 3.x reference.",
    )


def parse_heartbeat_report(value: object, params: dict[str, Any] | None = None) -> AirMessageMeaning | None:
    """Return a heartbeat reception report, excluding @HB beacon frames."""

    meaning = interpret_air_message(value, params)
    return meaning if meaning.kind == "heartbeat_report" else None
