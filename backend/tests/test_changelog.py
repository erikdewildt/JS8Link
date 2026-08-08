# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
from js8link.domain.changelog import parse_changelog


def test_parse_changelog_returns_releases_categories_and_items() -> None:
    result = parse_changelog(
        """# Changelog

## [Unreleased]

### Added

- A new feature.

## [1.2.3] - 2026-08-06

### Fixed

- A fixed bug.
"""
    )

    assert result == [
        {
            "version": "Unreleased",
            "date": None,
            "categories": [{"name": "Added", "items": ["A new feature."]}],
        },
        {
            "version": "1.2.3",
            "date": "2026-08-06",
            "categories": [{"name": "Fixed", "items": ["A fixed bug."]}],
        },
    ]
