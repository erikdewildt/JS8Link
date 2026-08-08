# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PrefixLocation:
    prefix: str
    country: str
    latitude: float
    longitude: float


def load_prefix_locations() -> tuple[PrefixLocation, ...]:
    path = Path(__file__).parents[1] / "data" / "callsign_prefixes.json"
    records = json.loads(path.read_text(encoding="utf-8"))
    return tuple(PrefixLocation(**record) for record in records)


PREFIX_LOCATIONS = load_prefix_locations()


def callsign_location(callsign: str | None) -> PrefixLocation | None:
    if not callsign:
        return None
    normalized = callsign.strip().upper().split("/", 1)[0]
    matches = [entry for entry in PREFIX_LOCATIONS if normalized.startswith(entry.prefix)]
    return max(matches, key=lambda entry: len(entry.prefix), default=None)
