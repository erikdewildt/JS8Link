# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
import sys
from pathlib import Path


def _resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[3]


_version_file = _resource_root() / "VERSION"
__version__ = _version_file.read_text(encoding="utf-8").strip()
