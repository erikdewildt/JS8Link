"""Static, localised help content for the JS8Link console."""

import json
from pathlib import Path
from typing import Any

HELP_ROOT = Path(__file__).parent
SUPPORTED_LANGUAGES = {"nl", "en"}


def load_catalog(language: str) -> dict[str, Any]:
    """Load a local help catalog, falling back to English for unknown languages."""
    selected = language if language in SUPPORTED_LANGUAGES else "en"
    path = HELP_ROOT / f"{selected}.json"
    with path.open(encoding="utf-8") as handle:
        catalog = json.load(handle)
    catalog["language"] = selected
    return catalog
