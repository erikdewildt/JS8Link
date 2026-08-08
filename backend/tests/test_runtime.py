# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
import os
from pathlib import Path

from js8link.runtime import configure_environment, default_data_dir, ensure_port_available, parse_args


def test_standalone_defaults_are_local_and_browser_enabled() -> None:
    args = parse_args([])

    assert args.host == "127.0.0.1"
    assert args.port == 8008
    assert args.no_browser is False
    assert default_data_dir().name == "JS8Link"


def test_runtime_options_configure_persistent_environment(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "application-data"

    configure_environment(data_dir=data_dir, host="127.0.0.1", port=18008)

    assert data_dir.is_dir()
    assert monkeypatch is not None
    assert os.environ["JS8LINK_DATA_DIR"] == str(data_dir)
    assert os.environ["JS8LINK_PORT"] == "18008"


def test_port_probe_allows_an_available_ephemeral_port() -> None:
    ensure_port_available("127.0.0.1", 0)
