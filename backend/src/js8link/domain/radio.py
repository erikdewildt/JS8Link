# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
from dataclasses import dataclass


@dataclass(frozen=True)
class BandRange:
    name: str
    low_hz: int
    high_hz: int


BAND_RANGES = (
    BandRange("2190m", 135_700, 137_800),
    BandRange("630m", 472_000, 479_000),
    BandRange("160m", 1_800_000, 2_000_000),
    BandRange("80m", 3_500_000, 4_000_000),
    BandRange("60m", 5_250_000, 5_450_000),
    BandRange("40m", 7_000_000, 7_300_000),
    BandRange("30m", 10_100_000, 10_150_000),
    BandRange("20m", 14_000_000, 14_350_000),
    BandRange("17m", 18_068_000, 18_168_000),
    BandRange("15m", 21_000_000, 21_450_000),
    BandRange("12m", 24_890_000, 24_990_000),
    BandRange("10m", 28_000_000, 29_700_000),
    BandRange("6m", 50_000_000, 54_000_000),
    BandRange("4m", 70_000_000, 70_500_000),
    BandRange("2m", 144_000_000, 148_000_000),
    BandRange("70cm", 420_000_000, 450_000_000),
)


def band_from_frequency(frequency_hz: object) -> str | None:
    try:
        frequency = int(frequency_hz)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return next((band.name for band in BAND_RANGES if band.low_hz <= frequency <= band.high_hz), None)
