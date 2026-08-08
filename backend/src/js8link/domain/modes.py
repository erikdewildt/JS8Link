# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
MODE_NAMES = {
    0: "Normal",
    1: "Fast",
    2: "Turbo",
    4: "Slow",
    8: "JS8 60",
}

MODE_BANDWIDTHS = {
    "Normal": 50,
    "Fast": 80,
    "Turbo": 160,
    "JS8 40": 160,
    "Slow": 25,
    "JS8 60": 250,
}


def mode_from_speed(speed: object) -> str | None:
    try:
        return MODE_NAMES.get(int(speed))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def bandwidth_from_mode(mode: str | None) -> int:
    """Return the nominal JS8 occupied bandwidth in Hz."""
    return MODE_BANDWIDTHS.get(mode or "Normal", MODE_BANDWIDTHS["Normal"])
