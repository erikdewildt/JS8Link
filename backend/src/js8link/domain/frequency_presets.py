# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FrequencyPreset:
    band: str
    dial: int
    label: str

    @property
    def frequency_mhz(self) -> float:
        return self.dial / 1_000_000


def load_frequency_presets() -> tuple[FrequencyPreset, ...]:
    path = Path(__file__).parents[1] / "data" / "js8_frequency_presets.json"
    values = json.loads(path.read_text(encoding="utf-8"))
    return tuple(FrequencyPreset(**value) for value in values)


FREQUENCY_PRESETS = load_frequency_presets()
