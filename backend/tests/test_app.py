# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
"""Smoke tests for the FastAPI application.

Tests the HTTP-level behaviour of key endpoints.  Background tasks and the
JS8Call client are mocked so no real network or JS8Call instance is needed.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

with (
    patch("asyncio.create_task", return_value=None),
    patch("js8link.app.connect_client", AsyncMock(return_value={
        "type": "STATION.VERSION",
        "params": {"VERSION": "3.0.0"},
        "value": "",
    })),
):
    from js8link.app import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestHealth:
    def test_health_returns_ok(self, client: TestClient) -> None:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestHelp:
    def test_help_catalog_is_localised_and_complete(self, client: TestClient) -> None:
        response = client.get("/api/help?lang=nl")
        assert response.status_code == 200
        data = response.json()
        assert data["language"] == "nl"
        assert {topic["id"] for topic in data["topics"]} >= {
            "global",
            "setup",
            "chat",
            "messages",
            "monitor",
            "settings",
            "diagnostics",
            "updates",
        }
        assert all(topic["title"] for topic in data["topics"])

    def test_unknown_help_language_falls_back_to_english(self, client: TestClient) -> None:
        response = client.get("/api/help?lang=fr")
        assert response.status_code == 200
        assert response.json()["language"] == "en"


class TestSetup:
    def test_setup_status_returns_fields(self, client: TestClient) -> None:
        response = client.get("/api/setup/status")
        assert response.status_code == 200
        data = response.json()
        assert "setup_complete" in data
        assert "host" in data
        assert "port" in data

    def test_test_connection_validation_empty_host(self, client: TestClient) -> None:
        response = client.post("/api/setup/test-connection", json={
            "host": "",
            "port": 2442,
        })
        assert response.status_code == 422

    def test_test_connection_validation_missing_fields(self, client: TestClient) -> None:
        response = client.post("/api/setup/test-connection", json={})
        assert response.status_code == 422


class TestAuth:
    def test_login_without_auth_configured(self, client: TestClient) -> None:
        response = client.post("/api/auth/login", json={
            "username": "admin",
            "password": "secret",
        })
        assert response.status_code == 200
        assert response.json()["authenticated"] is True

    def test_logout_get_not_allowed(self, client: TestClient) -> None:
        response = client.get("/api/auth/logout")
        assert response.status_code == 405


class TestMessages:
    def test_send_requires_connection(self, client: TestClient) -> None:
        response = client.post("/api/messages/send", json={
            "text": "Hello World",
        })
        assert response.status_code == 503

    def test_send_requires_text(self, client: TestClient) -> None:
        response = client.post("/api/messages/send", json={"text": ""})
        assert response.status_code == 422


class TestPreferences:
    def test_read_returns_keys(self, client: TestClient) -> None:
        response = client.get("/api/preferences")
        assert response.status_code == 200
        data = response.json()
        assert "language" in data
        assert "theme" in data


class TestStatus:
    def test_status_requires_connection(self, client: TestClient) -> None:
        response = client.get("/api/status")
        assert response.status_code == 503


class TestFrequencyPresets:
    def test_returns_list(self, client: TestClient) -> None:
        response = client.get("/api/js8/frequency-presets")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_each_preset_has_required_fields(self, client: TestClient) -> None:
        response = client.get("/api/js8/frequency-presets")
        for preset in response.json():
            assert "band" in preset
            assert "dial" in preset
            assert "label" in preset
            assert "frequency_mhz" in preset


class TestOffsets:
    def test_returns_band_and_offsets(self, client: TestClient) -> None:
        response = client.get("/api/js8/offsets")
        assert response.status_code == 200
        data = response.json()
        assert "band" in data
        assert isinstance(data["offsets"], list)

    def test_band_param_is_echoed(self, client: TestClient) -> None:
        response = client.get("/api/js8/offsets?band=20m")
        assert response.status_code == 200
        assert response.json()["band"] == "20m"
