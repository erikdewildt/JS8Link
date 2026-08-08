# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
import re
from pathlib import Path
from typing import Any

RELEASE_HEADING = re.compile(r"^## \[([^]]+)](?: - (\d{4}-\d{2}-\d{2}))?$")
CATEGORY_HEADING = re.compile(r"^### (.+)$")


def parse_changelog(content: str) -> list[dict[str, Any]]:
    releases: list[dict[str, Any]] = []
    current_release: dict[str, Any] | None = None
    current_category: dict[str, Any] | None = None

    for raw_line in content.splitlines():
        line = raw_line.strip()
        release_match = RELEASE_HEADING.match(line)
        if release_match:
            current_release = {
                "version": release_match.group(1),
                "date": release_match.group(2),
                "categories": [],
            }
            releases.append(current_release)
            current_category = None
            continue

        category_match = CATEGORY_HEADING.match(line)
        if category_match and current_release is not None:
            current_category = {"name": category_match.group(1), "items": []}
            current_release["categories"].append(current_category)
            continue

        if line.startswith("- ") and current_category is not None:
            current_category["items"].append(line[2:])

    return releases


def load_changelog(path: Path) -> list[dict[str, Any]]:
    return parse_changelog(path.read_text(encoding="utf-8"))
