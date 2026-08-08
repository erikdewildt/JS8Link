# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
from js8link.app import app


def test_initial_frontend_api_routes_are_registered() -> None:
    paths = {route.path for route in app.routes}
    assert {
        "/api/setup/status",
        "/api/setup/test-connection",
        "/api/setup/complete",
        "/api/auth/login",
        "/api/preferences",
        "/api/status",
        "/api/js8/frequency-presets",
        "/api/rig/frequency",
        "/api/mode/speed",
        "/api/events",
    } <= paths
