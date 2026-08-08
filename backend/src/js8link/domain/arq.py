# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
import logging
import re
import secrets
from dataclasses import dataclass

ARQ_VERSION = 1
ARQ_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
ARQ_SUFFIX = re.compile(
    r"(?:^|\s)~(?P<version>\d)(?P<opcode>[DA])(?P<message_id>[0-9A-HJKMNP-TV-Z]{6})\s*(?:♢)?\s*$",
    re.IGNORECASE,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ARQEnvelope:
    payload: str
    version: int
    opcode: str
    message_id: str


def new_message_id() -> str:
    return "".join(secrets.choice(ARQ_ALPHABET) for _ in range(6))


def encode_data(payload: str, message_id: str) -> str:
    return f"{payload.rstrip()} ~{ARQ_VERSION}D{message_id}"


def encode_ack(message_id: str) -> str:
    return f"~{ARQ_VERSION}A{message_id}"


def parse_envelope(value: object) -> ARQEnvelope | None:
    text = str(value or "").strip()
    match = ARQ_SUFFIX.search(text)
    if match is None:
        return None
    return ARQEnvelope(
        payload=text[: match.start()].strip(),
        version=int(match.group("version")),
        opcode=match.group("opcode").upper(),
        message_id=match.group("message_id").upper(),
    )


def ack_timeout_seconds(mode: str | None) -> int:
    return {
        "Fast": 45,
        "Turbo": 45,
        "Normal": 60,
        "Slow": 120,
        "JS8 40": 150,
        "JS8 60": 210,
    }.get(mode or "Normal", 60)
