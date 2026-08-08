# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
from js8link.domain.radio import band_from_frequency


def test_band_from_frequency() -> None:
    assert band_from_frequency(7_078_000) == "40m"
    assert band_from_frequency(14_074_000) == "20m"


def test_unknown_frequency_has_no_band() -> None:
    assert band_from_frequency(123_456) is None


def test_none_input_returns_none() -> None:
    assert band_from_frequency(None) is None


def test_string_frequency_is_parsed() -> None:
    assert band_from_frequency("7078000") == "40m"


def test_float_frequency_is_parsed() -> None:
    assert band_from_frequency(7_078_000.0) == "40m"


def test_invalid_string_returns_none() -> None:
    assert band_from_frequency("not-a-frequency") is None


def test_band_boundaries() -> None:
    assert band_from_frequency(1_800_000) == "160m"  # lower bound
    assert band_from_frequency(2_000_000) == "160m"  # upper bound
    assert band_from_frequency(1_799_999) is None  # just below


def test_all_bands_have_known_names() -> None:
    bands = {
        (135_700, "2190m"),
        (472_000, "630m"),
        (1_900_000, "160m"),
        (3_750_000, "80m"),
        (5_350_000, "60m"),
        (7_150_000, "40m"),
        (10_125_000, "30m"),
        (14_175_000, "20m"),
        (18_118_000, "17m"),
        (21_225_000, "15m"),
        (24_940_000, "12m"),
        (28_850_000, "10m"),
        (52_000_000, "6m"),
        (70_250_000, "4m"),
        (146_000_000, "2m"),
        (435_000_000, "70cm"),
    }
    for freq, expected in bands:
        assert band_from_frequency(freq) == expected, f"{freq} Hz should be {expected}"
