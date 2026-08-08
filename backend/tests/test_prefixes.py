# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
from js8link.domain.maidenhead import grid_to_coordinates
from js8link.domain.prefixes import callsign_location


def test_prefix_location_uses_longest_match() -> None:
    assert callsign_location("A45ABC").country == "Oman"
    assert callsign_location("PA0ABC/P").country == "Netherlands"


def test_prefix_location_is_fallback_data() -> None:
    location = callsign_location("DL1XYZ")
    assert location is not None
    assert location.country == "Germany"
    assert grid_to_coordinates("JO62") != (location.latitude, location.longitude)


def test_unknown_prefix_returns_none() -> None:
    assert callsign_location("ZZ9UNKNOWN") is None


def test_none_callsign_returns_none() -> None:
    assert callsign_location(None) is None


def test_empty_callsign_returns_none() -> None:
    assert callsign_location("") is None
