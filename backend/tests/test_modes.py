# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
from js8link.domain.modes import bandwidth_from_mode, mode_from_speed


class TestModeFromSpeed:
    def test_known_speeds(self) -> None:
        assert mode_from_speed(0) == "Normal"
        assert mode_from_speed(1) == "Fast"
        assert mode_from_speed(2) == "Turbo"
        assert mode_from_speed(4) == "Slow"
        assert mode_from_speed(8) == "JS8 60"

    def test_unknown_speed_returns_none(self) -> None:
        assert mode_from_speed(3) is None
        assert mode_from_speed(99) is None

    def test_none_input_returns_none(self) -> None:
        assert mode_from_speed(None) is None

    def test_string_is_converted(self) -> None:
        assert mode_from_speed("1") == "Fast"

    def test_invalid_string_returns_none(self) -> None:
        assert mode_from_speed("not-a-number") is None


class TestBandwidthFromMode:
    def test_known_modes(self) -> None:
        assert bandwidth_from_mode("Normal") == 50
        assert bandwidth_from_mode("Fast") == 80
        assert bandwidth_from_mode("Turbo") == 160
        assert bandwidth_from_mode("JS8 40") == 160
        assert bandwidth_from_mode("Slow") == 25
        assert bandwidth_from_mode("JS8 60") == 250

    def test_none_mode_defaults_to_normal(self) -> None:
        assert bandwidth_from_mode(None) == 50

    def test_unknown_mode_defaults_to_normal(self) -> None:
        assert bandwidth_from_mode("SuperFast") == 50

    def test_empty_string_defaults_to_normal(self) -> None:
        assert bandwidth_from_mode("") == 50
