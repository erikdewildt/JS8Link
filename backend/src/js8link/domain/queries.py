# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
"""Scheduling and parsing helpers for station queries."""

import re
from dataclasses import dataclass
from math import ceil

QUERY_COMMANDS = frozenset({"SNR", "HEARING", "INFO", "GRID", "STATUS", "MSGS"})

# Response to QUERY MSGS: one or more "MSG <id>" entries.
_MSGS_RESPONSE = re.compile(r"^MSG\s+\d+(?:\s+MSG\s+\d+)*$", re.IGNORECASE)
# Response to QUERY MSG <id>: the stored message text (any non-empty body).
# We cannot distinguish this from a regular message by text alone, so
# _handle_directed checks for a pending "msg" StationQuery instead.


@dataclass(frozen=True)
class QueryResponse:
    """Structured data extracted from a JS8Call query response."""

    command: str
    snr: int | None = None
    grid: str | None = None
    text: str | None = None
    hearing: tuple[dict[str, int | str], ...] = ()
    msg_ids: tuple[int, ...] = ()


def infer_query_command(command: object, body: object) -> str | None:
    """Identify a query response from its directed text.

    JS8Call commonly reports a directed query reply with ``CMD=MSG``.  The
    actual command is then present in the value, for example ``DF7ET SNR -12``.

    When a frame is partially decoded the command label may be missing;
    fall back to heuristics based on the shape of the remaining data.
    """
    normalized_command = str(command or "").strip().upper()
    if normalized_command in QUERY_COMMANDS:
        return normalized_command

    text = _clean_query_text(body)

    # Try explicit command labels first.
    match = re.match(
        r"^(?:[A-Z0-9/]{3,16}\s+)?(SNR|HEARING|INFO|GRID|STATUS)\b",
        text,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).upper()

    # Response to QUERY MSGS: "MSG 32 MSG 15 ..."
    if _MSGS_RESPONSE.match(text):
        return "MSGS"

    # Partial decode heuristics: when the command label is missing, infer
    # from the data shape.  These are only used when no explicit label exists.
    #
    # SNR:  a bare signed integer (e.g. "-12" or "+05").
    if re.fullmatch(r"[+-]?\d{1,2}", text):
        return "SNR"
    # GRID: a bare 4- or 6-character Maidenhead locator.
    if re.fullmatch(r"[A-R]{2}\d{2}(?:[A-X]{2})?", text, re.IGNORECASE):
        return "GRID"

    # Response to QUERY MSG <id>: the body is the stored message text.
    # We cannot identify it from text alone — the caller must check for a
    # pending StationQuery of type "msg" when this returns None.
    return None


def parse_query_response(command: str, body: object) -> QueryResponse | None:
    """Parse a response body returned by a JS8Call station query.

    The parser accepts both the displayed form (``CALLSIGN: ...`` after the
    sender prefix has been removed) and the compact forms used by different
    JS8Call-improved versions.  The diamond terminator is display metadata,
    not part of the response value.
    """
    normalized = _clean_query_text(body)
    command = command.strip().upper()

    if command == "SNR":
        match = re.search(r"\bSNR\s*[:=]?\s*([+-]?\d+)\b", normalized, re.IGNORECASE)
        if match is None:
            match = re.fullmatch(r"([+-]?\d+)", normalized)
        return QueryResponse(command, snr=int(match.group(1))) if match else None

    if command == "GRID":
        match = re.search(r"\bGRID\s*[:=]?\s*([A-Z]{2}\d{2}(?:[A-Z]{2})?)\b", normalized, re.IGNORECASE)
        if match is None:
            match = re.fullmatch(r"([A-Z]{2}\d{2}(?:[A-Z]{2})?)", normalized, re.IGNORECASE)
        return QueryResponse(command, grid=match.group(1).upper()) if match else None

    if command in {"INFO", "STATUS"}:
        match = re.search(rf"\b{command}\s*[:=]?\s*(.+)$", normalized, re.IGNORECASE)
        if match:
            return QueryResponse(command, text=match.group(1).strip())
        return None

    if command == "HEARING":
        entries: list[dict[str, int | str]] = []
        # Try full "CALLSIGN SNR -12" pairs first.
        for match in re.finditer(
            r"\b(?P<callsign>[A-Z0-9/]{3,16})\s+(?:SNR\s*[:=]?\s*)?(?P<snr>-?\d+)\b",
            normalized,
            re.IGNORECASE,
        ):
            callsign = match.group("callsign").upper()
            if callsign == "HEARING":
                continue
            entries.append({"callsign": callsign, "snr": int(match.group("snr"))})
        # Accept callsigns without SNR when the frame was partially decoded.
        if not entries:
            for match in re.finditer(
                r"\b(?P<callsign>[A-Z0-9/]{3,16})\b",
                normalized,
                re.IGNORECASE,
            ):
                callsign = match.group("callsign").upper()
                if callsign in {"HEARING", "HEARING?"}:
                    continue
                entries.append({"callsign": callsign, "snr": 0})
        return QueryResponse(command, hearing=tuple(entries)) if entries else None

    if command == "MSGS":
        ids = [int(m.group(1)) for m in re.finditer(r"MSG\s+(\d+)", normalized, re.IGNORECASE)]
        return QueryResponse(command, msg_ids=tuple(ids), text=normalized) if ids else None

    if command == "MSG":
        # Response to QUERY MSG <id>: the body is the stored message.
        return QueryResponse(command, text=normalized) if normalized else None

    return None


def _clean_query_text(value: object) -> str:
    return re.sub(r"\s*♢\s*$", "", str(value or "").strip())


def query_spacing_seconds(max_queries_per_hour: int, minimum_seconds: int) -> int:
    """Return the spacing needed to distribute an hourly query budget.

    The configured cooldown remains a safety floor, while the hourly budget
    determines the normal spacing. For example, 12 queries/hour results in
    one query every 300 seconds instead of every 120 seconds.
    """
    if max_queries_per_hour <= 0:
        return max(minimum_seconds, 3600)
    return max(minimum_seconds, ceil(3600 / max_queries_per_hour))
