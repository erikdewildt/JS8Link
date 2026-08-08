# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
from js8link.domain.frequency_presets import FREQUENCY_PRESETS


def test_current_js8call_frequency_presets_are_loaded() -> None:
    assert len(FREQUENCY_PRESETS) == 12
    assert FREQUENCY_PRESETS[0].dial == 1_843_500
    assert FREQUENCY_PRESETS[2].band == "60m"
    assert FREQUENCY_PRESETS[2].dial == 5_363_000
    assert FREQUENCY_PRESETS[-1].band == "2m"


def test_frequency_preset_labels_include_mhz() -> None:
    assert all("MHz" in preset.label for preset in FREQUENCY_PRESETS)
    assert all(preset.frequency_mhz > 0 for preset in FREQUENCY_PRESETS)
