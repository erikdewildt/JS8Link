# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
from js8link.app import app


def test_chat_frontend_api_routes_are_registered() -> None:
    paths = {route.path for route in app.routes}
    assert {
        "/api/chats",
        "/api/chats/stations",
        "/api/chats/{callsign:path}/messages",
        "/api/chats/{callsign:path}/read",
        "/api/stations/{callsign:path}",
        "/api/chats/{callsign:path}/archive",
    } <= paths
