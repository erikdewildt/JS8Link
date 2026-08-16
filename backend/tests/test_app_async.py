# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
"""Comprehensive async tests for the JS8Link FastAPI application.

Uses httpx.AsyncClient with ASGITransport along with an in-memory SQLite
database and a mocked JS8Call client to exercise every endpoint.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from js8link.app import (
    _cleanup_retained_messages,
    _find_received_frame_duplicate,
    _handle_activity,
    _handle_directed,
    _handle_query_response,
    _handle_tx_frame,
    _merge_received_frame,
)
from js8link.models import (
    AppConfig,
    DiagnosticProcessing,
    DiagnosticTrace,
    JS8APIMessage,
    ReceivedMessage,
    Station,
    StationLink,
    StationQuery,
    TransmittedMessage,
)

# ============================================================================
# Status endpoints
# ============================================================================


class TestStatusEndpoints:
    @pytest.mark.asyncio
    async def test_health_returns_ok_and_connected(self, async_client) -> None:
        response = await async_client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["connected"] is True
        assert "version" in data

    @pytest.mark.asyncio
    async def test_health_returns_disconnected(self, async_client_disconnected) -> None:
        response = await async_client_disconnected.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["connected"] is False

    @pytest.mark.asyncio
    async def test_status_with_connected_client(self, async_client) -> None:
        response = await async_client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is True
        # Radio state must be read from RIG.GET_FREQ + MODE.GET_SPEED (the mock
        # returns DIAL=14074000, OFFSET=1500, SPEED=0).
        assert data["dial"] == 14074000
        assert data["offset"] == 1500
        assert data["speed"] == 0
        assert data["band"] == "20m"
        assert data["mode_name"] == "Normal"
        assert data["grid"] == "FN42"
        assert data["info"] == "JS8Link Test"
        assert data["status_text"] == "Testing"
        assert data["normal_offset"] == 1500
        assert data["tx_queue_depth"] == 0
        assert data["rx_enabled"] is True
        assert data["tx_enabled"] is True

    @pytest.mark.asyncio
    async def test_rx_toggle_disables_processing(self, async_client, mock_js8call) -> None:
        # Disable RX: status reflects it.
        response = await async_client.post("/api/js8/rx-toggle", json={"enabled": False})
        assert response.status_code == 200
        assert response.json()["rx_enabled"] is False
        assert response.json()["scope"] == "js8link"
        mock_js8call.send.assert_not_awaited()
        status = (await async_client.get("/api/status")).json()
        assert status["rx_enabled"] is False
        # Re-enable for other tests in the same app instance.
        await async_client.post("/api/js8/rx-toggle", json={"enabled": True})

    @pytest.mark.asyncio
    async def test_tx_toggle_blocks_transmission(self, async_client, mock_js8call) -> None:
        response = await async_client.post("/api/js8/tx-toggle", json={"enabled": False})
        assert response.status_code == 200
        assert response.json()["tx_enabled"] is False
        mock_js8call.send.assert_awaited_once_with("RIG.TX_HALT")
        # Sending while TX is disabled should fail with an error.
        send = await async_client.post("/api/messages/send", json={"text": "Hello", "callsign": "PA3ABC"})
        assert send.status_code >= 400
        heartbeat = await async_client.post("/api/js8/send-hb")
        assert heartbeat.status_code == 409
        mock_js8call.send.assert_awaited_once_with("RIG.TX_HALT")
        status = (await async_client.get("/api/status")).json()
        assert status["tx_enabled"] is False
        await async_client.post("/api/js8/tx-toggle", json={"enabled": True})

    @pytest.mark.asyncio
    async def test_status_requires_connection(self, async_client_disconnected) -> None:
        response = await async_client_disconnected.get("/api/status")
        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_call_selected_poll_returns_empty_when_disconnected(
        self, async_client_disconnected
    ) -> None:
        response = await async_client_disconnected.get("/api/js8/call-selected")
        assert response.status_code == 200
        assert response.json() == {"callsign": None}

    @pytest.mark.asyncio
    async def test_call_selected_endpoint_reads_and_sets_selection(self, async_client, mock_js8call) -> None:
        response = await async_client.get("/api/js8/call-selected")
        assert response.status_code == 200
        assert response.json() == {"callsign": None}

        selected = await async_client.patch(
            "/api/js8/call-selected",
            json={"callsign": "DF7ET"},
        )
        assert selected.status_code == 200
        assert selected.json() == {"callsign": "DF7ET"}
        mock_js8call.send.assert_awaited_once_with("RX.CALL_SELECTED", value="DF7ET")

    @pytest.mark.asyncio
    async def test_clear_call_selected_reports_unsupported_js8call_api(
        self, async_client, mock_js8call
    ) -> None:
        original_request = mock_js8call.request.side_effect

        async def selected_after_clear(message_type: str, value: str = "", params: dict | None = None):
            if message_type == "RX.GET_CALL_SELECTED":
                return {"type": "RX.CALL_SELECTED", "params": {}, "value": "F6HCM"}
            return await original_request(message_type, value, params)

        mock_js8call.request.side_effect = selected_after_clear
        response = await async_client.post("/api/js8/call-selected/clear")
        assert response.status_code == 409
        assert response.status_code == 409
        assert "no api command" in response.json()["detail"].lower()


# ============================================================================
# Config endpoints
# ============================================================================


class TestConfigEndpoints:
    @pytest.mark.asyncio
    async def test_get_config_returns_fields(self, async_client) -> None:
        response = await async_client.get("/api/config")
        assert response.status_code == 200
        data = response.json()
        assert "host" in data
        assert "port" in data
        assert "auth_enabled" in data
        assert "setup_complete" in data

    @pytest.mark.asyncio
    async def test_patch_config_updates_host(self, async_client) -> None:
        patch_response = await async_client.patch("/api/config", json={"host": "10.0.0.1"})
        assert patch_response.status_code == 200

        get_response = await async_client.get("/api/config")
        assert get_response.json()["host"] == "10.0.0.1"

    @pytest.mark.asyncio
    async def test_api_message_retention_is_configurable(self, async_client) -> None:
        response = await async_client.patch("/api/config", json={"api_message_retention_days": 14})
        assert response.status_code == 200
        assert (await async_client.get("/api/config")).json()["api_message_retention_days"] == 14

    @pytest.mark.asyncio
    async def test_station_information_queries_can_be_disabled(self, async_client) -> None:
        patch_response = await async_client.patch(
            "/api/config", json={"station_queries_enabled": False}
        )
        assert patch_response.status_code == 200

        config = await async_client.get("/api/config")
        assert config.json()["station_queries_enabled"] is False

        query = await async_client.post(
            "/api/stations/PA3ABC/query", json={"query_type": "snr"}
        )
        # The setting only controls the background scheduler; explicit user
        # queries still reach normal station validation.
        assert query.status_code == 404


# ============================================================================
# Preferences endpoints
# ============================================================================


class TestPreferencesEndpoints:
    @pytest.mark.asyncio
    async def test_get_preferences(self, async_client) -> None:
        response = await async_client.get("/api/preferences")
        assert response.status_code == 200
        data = response.json()
        assert "language" in data
        assert "theme" in data
        assert data["toast_duration_seconds"] == 5

    @pytest.mark.asyncio
    async def test_patch_preferences(self, async_client) -> None:
        patch_response = await async_client.patch(
            "/api/preferences", json={"theme": "light", "time_display": "utc"}
        )
        assert patch_response.status_code == 200

        get_response = await async_client.get("/api/preferences")
        assert get_response.json()["theme"] == "light"
        assert get_response.json()["time_display"] == "utc"

        forest_response = await async_client.patch(
            "/api/preferences", json={"theme": "forest"}
        )
        assert forest_response.status_code == 200
        assert (await async_client.get("/api/preferences")).json()["theme"] == "forest"

        field_light_response = await async_client.patch(
            "/api/preferences", json={"theme": "field-light"}
        )
        assert field_light_response.status_code == 200
        assert (await async_client.get("/api/preferences")).json()["theme"] == "field-light"

    @pytest.mark.asyncio
    async def test_band_scope_accepts_up_to_24_hours(self, async_client) -> None:
        response = await async_client.patch("/api/preferences", json={"band_scope_minutes": 1440})
        assert response.status_code == 200
        assert (await async_client.get("/api/preferences")).json()["band_scope_minutes"] == 1440


class TestRetention:
    @pytest.mark.asyncio
    async def test_api_diagnostics_and_band_activity_retention(self, async_session: AsyncSession) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        config = AppConfig(received_message_retention_days=90, api_message_retention_days=7)
        async_session.add(config)
        async_session.add_all(
            [
                JS8APIMessage(
                    direction="RX",
                    message_type="RX.BAND_ACTIVITY",
                    params_json="{}",
                    value_json="{}",
                    raw_payload="{}",
                    received_at=now - timedelta(days=2),
                ),
                JS8APIMessage(
                    direction="RX",
                    message_type="RX.DIRECTED",
                    params_json="{}",
                    value_json="{}",
                    raw_payload="{}",
                    received_at=now - timedelta(days=8),
                ),
                JS8APIMessage(
                    direction="RX",
                    message_type="RX.BAND_ACTIVITY",
                    params_json="{}",
                    value_json="{}",
                    raw_payload="{}",
                    received_at=now,
                ),
            ]
        )
        await async_session.commit()

        await _cleanup_retained_messages(async_session, config)

        remaining = (await async_session.scalars(select(JS8APIMessage))).all()
        assert [message.message_type for message in remaining] == ["RX.BAND_ACTIVITY"]


class TestDiagnosticsEndpoints:
    @pytest.mark.asyncio
    async def test_diagnostic_trace_detail_filters_and_purge(self, async_client, async_session: AsyncSession) -> None:
        async_session.add(AppConfig(language="nl", theme="dark"))
        async_session.add(
            DiagnosticTrace(
                trace_id="trace-edge-1",
                source="js8_api",
                event_type="RX.ACTIVITY",
                severity="warning",
                summary="Raw summary",
                interpretation="Raw interpretation",
                raw_payload='{"type":"RX.ACTIVITY","params":{"SNR":-12},"value":"N0CALL: CQ"}',
            )
        )
        async_session.add(
            DiagnosticProcessing(
                trace_id="trace-edge-1",
                sequence=1,
                operation="Classify frame",
                outcome="ok",
                detail="Stored as band activity",
                payload='{"kind":"band_activity"}',
            )
        )
        await async_session.commit()

        filtered = await async_client.get("/api/diagnostics/traces?source=js8_api&severity=warning")
        assert filtered.status_code == 200
        assert [trace["trace_id"] for trace in filtered.json()["traces"]] == ["trace-edge-1"]
        assert filtered.json()["traces"][0]["summary"] == "CQ call received"

        detail = await async_client.get("/api/diagnostics/traces/trace-edge-1")
        assert detail.status_code == 200
        assert detail.json()["processing"][0]["operation"] == "Classify frame"
        assert "RX.ACTIVITY" in detail.json()["raw_payload"]

        purged = await async_client.post("/api/diagnostics/purge")
        assert purged.status_code == 200
        assert purged.json()["deleted"]["diagnostic_traces"] == 1
        assert (await async_client.get("/api/diagnostics/traces")).json()["traces"] == []
        assert (await async_client.get("/api/config")).status_code == 200

    @pytest.mark.asyncio
    async def test_diagnostic_trace_limit_is_validated(self, async_client) -> None:
        response = await async_client.get("/api/diagnostics/traces?limit=0")

        assert response.status_code == 422


class TestBandActivityProcessing:
    @pytest.mark.asyncio
    async def test_heartbeat_beacon_uses_beacon_persistence_handler(self, monkeypatch) -> None:
        calls: list[tuple[object, ...]] = []

        async def record_beacon(*args, **kwargs) -> None:
            calls.append((*args, kwargs))

        monkeypatch.setattr("js8link.app.local_callsign", "PE1PUX")
        monkeypatch.setattr("js8link.app._record_band_activity_heartbeat_beacon", record_beacon)

        await _handle_activity(
            {"type": "RX.BAND_ACTIVITY"},
            "RX.BAND_ACTIVITY",
            {"SNR": -10, "OFFSET": 700},
            "M0XRS: @HB HEARTBEAT IO83",
        )

        assert len(calls) == 1
        assert calls[0][0:2] == ("M0XRS", "IO83")
        assert calls[0][2] == {"SNR": -10, "OFFSET": 700}

    @pytest.mark.asyncio
    async def test_local_heartbeat_response_is_stored_as_transmitted_monitor_traffic(
        self, async_session: AsyncSession, async_engine, monkeypatch
    ) -> None:
        monkeypatch.setattr("js8link.app.local_callsign", "PE1PUX")
        monkeypatch.setattr("js8link.app.SessionLocal", async_sessionmaker(async_engine, expire_on_commit=False))

        await _handle_activity(
            {
                "type": "RX.ACTIVITY",
                "params": {"DIAL": 7078000, "OFFSET": 700, "SPEED": 0},
            },
            "RX.ACTIVITY",
            {"DIAL": 7078000, "OFFSET": 700, "SPEED": 0},
            "PE1PUX: M0XRS HEARTBEAT SNR -12",
        )

        transmitted = (await async_session.scalars(select(TransmittedMessage))).all()
        assert len(transmitted) == 1
        assert transmitted[0].text == "PE1PUX: M0XRS HEARTBEAT SNR -12"

    @pytest.mark.asyncio
    async def test_repeated_heartbeat_response_after_dedup_window_is_stored(
        self, async_session: AsyncSession, async_engine, monkeypatch
    ) -> None:
        monkeypatch.setattr("js8link.app.local_callsign", "PE1PUX")
        monkeypatch.setattr("js8link.app.SessionLocal", async_sessionmaker(async_engine, expire_on_commit=False))
        async_session.add(
            TransmittedMessage(
                callsign="PE1PUX",
                text="PE1PUX M0XRS HEARTBEAT SNR -12",
                status="sent",
                tx_frame_type="TX.FRAME",
                transmitted_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=20),
            )
        )
        await async_session.commit()

        await _handle_activity(
            {"type": "RX.ACTIVITY", "params": {"DIAL": 7078000, "OFFSET": 700, "SPEED": 0}},
            "RX.ACTIVITY",
            {"DIAL": 7078000, "OFFSET": 700, "SPEED": 0},
            "PE1PUX: M0XRS HEARTBEAT SNR -12",
        )

        transmitted = (await async_session.scalars(select(TransmittedMessage))).all()
        assert len(transmitted) == 2

    @pytest.mark.asyncio
    async def test_local_directed_heartbeat_is_stored_as_transmitted_monitor_traffic(
        self, async_session: AsyncSession, async_engine, monkeypatch
    ) -> None:
        monkeypatch.setattr("js8link.app.local_callsign", "PE1PUX")
        monkeypatch.setattr("js8link.app.SessionLocal", async_sessionmaker(async_engine, expire_on_commit=False))

        await _handle_directed(
            {
                "type": "RX.DIRECTED",
                "value": "PE1PUX: @HB HEARTBEAT IO83",
                "params": {
                    "FROM": "PE1PUX",
                    "TO": "@HB",
                    "CMD": " HEARTBEAT",
                    "DIAL": 7078000,
                    "OFFSET": 700,
                    "SPEED": 0,
                },
            },
            {
                "FROM": "PE1PUX",
                "TO": "@HB",
                "CMD": " HEARTBEAT",
                "DIAL": 7078000,
                "OFFSET": 700,
                "SPEED": 0,
            },
            "PE1PUX: @HB HEARTBEAT IO83",
        )

        transmitted = (await async_session.scalars(select(TransmittedMessage))).all()
        assert len(transmitted) == 1
        assert transmitted[0].text == "PE1PUX @HB HEARTBEAT IO83"

    @pytest.mark.asyncio
    async def test_tone_only_automatic_response_inherits_latest_radio_metadata(
        self, async_session: AsyncSession, async_engine, monkeypatch
    ) -> None:
        monkeypatch.setattr("js8link.app.local_callsign", "PE1PUX")
        monkeypatch.setattr("js8link.app.SessionLocal", async_sessionmaker(async_engine, expire_on_commit=False))
        monkeypatch.setattr(
            "js8link.app.tx_state",
            {
                "last_dial": 7078000,
                "last_offset": 700,
                "last_speed": 0,
                "pending_heartbeat_response": {
                    "text": "PE1PUX M0XRS HEARTBEAT SNR -12",
                    "queued_at": datetime.now(UTC).replace(tzinfo=None),
                },
            },
        )

        await _handle_tx_frame({"type": "TX.FRAME"}, {"TONES": [1, 2, 3]}, "")

        transmitted = (await async_session.scalars(select(TransmittedMessage))).all()
        assert len(transmitted) == 1
        assert transmitted[0].text == "PE1PUX M0XRS HEARTBEAT SNR -12"
        assert transmitted[0].band == "40m"
        assert transmitted[0].offset == 700


class TestReceivedFrameDeduplication:
    @pytest.mark.asyncio
    async def test_activity_and_directed_events_are_one_frame(self, async_session: AsyncSession) -> None:
        timestamp = datetime(2026, 8, 7, 14, 13, 41)
        activity = ReceivedMessage(
            callsign="F4LFV/P",
            text="PE1PUX MESSAGE SNR -01",
            message_type="RX.ACTIVITY",
            kind="band_activity",
            delivery_mode="best_effort",
            offset=None,
            snr=None,
            utc_timestamp=timestamp,
            raw_payload="F4LFV/P: PE1PUX MESSAGE SNR -01 ♢",
        )
        async_session.add(activity)
        await async_session.commit()

        duplicate = await _find_received_frame_duplicate(
            async_session,
            sender="F4LFV/P",
            text="PE1PUX MESSAGE SNR -01",
            timestamp=timestamp.replace(tzinfo=UTC),
            offset=1179,
            snr=-1,
        )

        assert duplicate is activity
        directed = ReceivedMessage(
            callsign="F4LFV/P",
            text=activity.text,
            message_type="RX.DIRECTED",
            kind="direct_message",
            delivery_mode="best_effort",
            from_callsign="F4LFV/P",
            to_callsign="PE1PUX",
            offset=1179,
            snr=-1,
            utc_timestamp=timestamp,
            raw_payload="F4LFV/P: PE1PUX MESSAGE SNR -01 ♢",
        )
        _merge_received_frame(activity, directed)
        await async_session.commit()

        stored = (await async_session.scalars(select(ReceivedMessage))).all()
        assert len(stored) == 1
        assert stored[0].message_type == "RX.DIRECTED"
        assert stored[0].kind == "direct_message"
        assert stored[0].offset == 1179
        assert stored[0].snr == -1

    @pytest.mark.asyncio
    async def test_incomplete_duplicate_does_not_clear_delivery_mode(
        self, async_session: AsyncSession
    ) -> None:
        timestamp = datetime(2026, 8, 7, 14, 13, 41)
        existing = ReceivedMessage(
            callsign="LA7HKA",
            text="F4LFV/P SNR -16",
            message_type="RX.ACTIVITY",
            kind="band_activity",
            delivery_mode="best_effort",
            utc_timestamp=timestamp,
        )
        incoming = ReceivedMessage(
            callsign="LA7HKA",
            text=existing.text,
            message_type="RX.DIRECTED",
            kind="directed_control",
            delivery_mode=None,
            utc_timestamp=timestamp,
        )

        _merge_received_frame(existing, incoming)

        assert existing.delivery_mode == "best_effort"


# ============================================================================
# Auth endpoints
# ============================================================================


class TestAuthEndpoints:
    @pytest.mark.asyncio
    async def test_login_without_auth(self, async_client) -> None:
        response = await async_client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "secret"},
        )
        assert response.status_code == 200
        assert response.json()["authenticated"] is True

    @pytest.mark.asyncio
    async def test_logout_post(self, async_client) -> None:
        response = await async_client.post("/api/auth/logout")
        assert response.status_code == 200
        assert response.json()["authenticated"] is False


# ============================================================================
# Messages endpoints
# ============================================================================


class TestMessagesEndpoints:
    @pytest.mark.asyncio
    async def test_send_waits_for_tx_buffer_before_changing_selected_call(
        self, async_client, mock_js8call
    ) -> None:
        original_request = mock_js8call.request.side_effect
        buffer_reads = 0

        async def request(message_type: str, value: str = "", params: dict | None = None):
            nonlocal buffer_reads
            if message_type == "RX.GET_CALL_SELECTED":
                return {"type": "RX.CALL_SELECTED", "params": {}, "value": "OLD1"}
            if message_type == "TX.GET_TEXT":
                buffer_reads += 1
                return {
                    "type": "TX.TEXT",
                    "params": {},
                    "value": "still editing" if buffer_reads == 1 else "",
                }
            return await original_request(message_type, value, params)

        mock_js8call.request.side_effect = request
        response = await async_client.post(
            "/api/messages/send",
            json={"text": "Hello", "callsign": "NEW1"},
        )

        assert response.status_code == 200
        assert buffer_reads == 2
        assert [call.args[0] for call in mock_js8call.send.await_args_list[-2:]] == [
            "RX.CALL_SELECTED",
            "TX.SEND_MESSAGE",
        ]

    @pytest.mark.asyncio
    async def test_send_best_effort_message(self, async_client) -> None:
        response = await async_client.post(
            "/api/messages/send",
            json={"text": "Hello World"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sent"
        assert data["delivery_mode"] == "best_effort"

    @pytest.mark.asyncio
    async def test_send_confirmed_message(self, async_client) -> None:
        response = await async_client.post(
            "/api/messages/send",
            json={"text": "Important message", "delivery_mode": "confirmed"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["delivery_mode"] == "confirmed"

    @pytest.mark.asyncio
    async def test_send_requires_text(self, async_client) -> None:
        response = await async_client.post("/api/messages/send", json={"text": ""})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_send_requires_connection(self, async_client_disconnected) -> None:
        response = await async_client_disconnected.post(
            "/api/messages/send",
            json={"text": "Hello World"},
        )
        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_get_messages_empty(self, async_client) -> None:
        response = await async_client.get("/api/messages")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_get_messages_with_data(self, async_client, async_session: AsyncSession) -> None:
        msg = ReceivedMessage(
            id=1,
            text="Hello from K1ABC",
            callsign="K1ABC",
            from_callsign="K1ABC",
            kind="direct_message",
            delivery_mode="best_effort",
            band="20m",
            snr=5,
            received_at=datetime.now(UTC),
        )
        async_session.add(msg)
        await async_session.commit()

        response = await async_client.get("/api/messages")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["text"] == "Hello from K1ABC"
        assert data[0]["callsign"] == "K1ABC"


# ============================================================================
# Monitor endpoints
# ============================================================================


class TestMonitorEndpoints:
    @pytest.mark.asyncio
    async def test_monitor_returns_empty(self, async_client) -> None:
        response = await async_client.get("/api/monitor")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_monitor_stations_empty(self, async_client) -> None:
        response = await async_client.get("/api/monitor/stations")
        assert response.status_code == 200
        assert response.json() == []


# ============================================================================
# Setup endpoints
# ============================================================================


class TestSetupEndpoints:
    @pytest.mark.asyncio
    async def test_setup_status(self, async_client) -> None:
        response = await async_client.get("/api/setup/status")
        assert response.status_code == 200
        data = response.json()
        assert "setup_complete" in data
        assert "host" in data
        assert "port" in data
        assert "connected" in data

    @pytest.mark.asyncio
    async def test_setup_complete(self, async_client) -> None:
        response = await async_client.post(
            "/api/setup/complete",
            json={
                "host": "127.0.0.1",
                "port": 2442,
                "auth_enabled": False,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


# ============================================================================
# Offsets endpoints
# ============================================================================


class TestOffsetsEndpoints:
    @pytest.mark.asyncio
    async def test_offsets_default_band(self, async_client) -> None:
        response = await async_client.get("/api/js8/offsets")
        assert response.status_code == 200
        data = response.json()
        assert "band" in data
        assert isinstance(data["offsets"], list)


# ============================================================================
# Rig control endpoints
# ============================================================================


class TestRigEndpoints:
    @pytest.mark.asyncio
    async def test_get_rig_not_connected(self, async_client_disconnected) -> None:
        response = await async_client_disconnected.get("/api/rig")
        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_set_rig_not_connected(self, async_client_disconnected) -> None:
        response = await async_client_disconnected.post(
            "/api/rig/frequency",
            json={"dial": 14074000, "offset": 1500},
        )
        assert response.status_code == 503


# ============================================================================
# Mode control endpoints
# ============================================================================


class TestModeEndpoints:
    @pytest.mark.asyncio
    async def test_get_mode_not_connected(self, async_client_disconnected) -> None:
        response = await async_client_disconnected.get("/api/mode")
        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_set_mode_not_connected(self, async_client_disconnected) -> None:
        response = await async_client_disconnected.post("/api/mode/speed", json={"speed": 0})
        assert response.status_code == 503


# ============================================================================
# Chat endpoints
# ============================================================================


class TestChatEndpoints:
    @pytest.mark.asyncio
    async def test_chats_empty(self, async_client) -> None:
        response = await async_client.get("/api/chats")
        assert response.status_code == 200
        data = response.json()
        assert "chats" in data
        assert data["chats"] == []

    @pytest.mark.asyncio
    async def test_chat_stations_empty(self, async_client) -> None:
        response = await async_client.get("/api/chats/stations")
        assert response.status_code == 200
        data = response.json()
        assert "stations" in data
        assert data["stations"] == []

    @pytest.mark.asyncio
    async def test_chat_messages_unknown(self, async_client) -> None:
        response = await async_client.get("/api/chats/UNKNOWN/messages")
        assert response.status_code == 200
        data = response.json()
        assert "messages" in data
        assert data["messages"] == []

    @pytest.mark.asyncio
    async def test_heartbeat_rows_are_excluded_from_chat_history(
        self, async_client, async_session: AsyncSession
    ) -> None:
        async_session.add_all(
            [
                ReceivedMessage(
                    callsign="PA3ABC",
                    from_callsign="PA3ABC",
                    kind="direct_message",
                    delivery_mode="best_effort",
                    is_heartbeat=True,
                    text="PA3ABC HEARTBEAT SNR -12",
                ),
                ReceivedMessage(
                    callsign="PA3ABC",
                    from_callsign="PA3ABC",
                    kind="direct_message",
                    delivery_mode="best_effort",
                    is_heartbeat=False,
                    text="Hello",
                ),
            ]
        )
        await async_session.commit()

        chats = (await async_client.get("/api/chats")).json()["chats"]
        messages = (await async_client.get("/api/chats/PA3ABC/messages")).json()["messages"]

        assert len(chats) == 1
        assert [message["text"] for message in messages] == ["Hello"]

    @pytest.mark.asyncio
    async def test_locally_transmitted_heartbeat_responses_are_excluded_from_chats(
        self, async_client, async_session: AsyncSession
    ) -> None:
        async_session.add(
            TransmittedMessage(
                callsign="PE1PUX",
                text="PE1PUX M0XRS HEARTBEAT SNR +07",
                status="sent",
                delivery_mode="best_effort",
                tx_frame_type="TX.FRAME",
                is_heartbeat=True,
            )
        )
        await async_session.commit()

        assert (await async_client.get("/api/chats")).json()["chats"] == []
        assert (await async_client.get("/api/chats/PE1PUX/messages")).json()["messages"] == []

    @pytest.mark.asyncio
    async def test_chat_can_be_archived_and_restored(self, async_client, async_session: AsyncSession) -> None:
        async_session.add(
            ReceivedMessage(
                callsign="F4LFV/P",
                from_callsign="F4LFV/P",
                kind="direct_message",
                delivery_mode="best_effort",
                text="Hello",
            )
        )
        await async_session.commit()

        archive = await async_client.post("/api/chats/F4LFV%2FP/archive", json={"enabled": True})
        assert archive.status_code == 200
        assert archive.json()["archived"] is True
        archived = (await async_client.get("/api/chats")).json()["chats"]
        assert archived[0]["archived"] is True

        restore = await async_client.post("/api/chats/F4LFV%2FP/archive", json={"enabled": False})
        assert restore.status_code == 200
        restored = (await async_client.get("/api/chats")).json()["chats"]
        assert restored[0]["archived"] is False

        archive_again = await async_client.post("/api/chats/F4LFV%2FP/archive", json={"enabled": True})
        assert archive_again.json()["archived"] is True
        sent = await async_client.post(
            "/api/chats/F4LFV%2FP/messages",
            json={"text": "New activity"},
        )
        assert sent.status_code == 200
        active_after_send = (await async_client.get("/api/chats")).json()["chats"]
        assert active_after_send[0]["archived"] is False

    @pytest.mark.asyncio
    async def test_chat_speed_is_persisted(self, async_client, async_session: AsyncSession) -> None:
        async_session.add(
            ReceivedMessage(
                callsign="PA3ABC",
                from_callsign="PA3ABC",
                kind="direct_message",
                delivery_mode="best_effort",
                text="Hello",
            )
        )
        await async_session.commit()

        initial = (await async_client.get("/api/chats")).json()["chats"]
        assert initial[0]["preferred_speed"] == 0
        response = await async_client.patch("/api/chats/PA3ABC/speed", json={"speed": 1})
        assert response.status_code == 200
        assert response.json()["preferred_speed"] == 1
        restored = (await async_client.get("/api/chats")).json()["chats"]
        assert restored[0]["preferred_speed"] == 1


# ============================================================================
# Graph endpoint
# ============================================================================


class TestGraphEndpoint:
    @pytest.mark.asyncio
    async def test_monitor_graph_assigns_local_reception_snr_to_local_endpoint(
        self, async_client, async_session: AsyncSession
    ) -> None:
        now = datetime.now(UTC).replace(tzinfo=None)
        own = Station(
            callsign="PE1PUX",
            grid="JO22",
            latitude=52.1,
            longitude=5.1,
            last_seen=now,
            message_count=0,
        )
        remote = Station(
            callsign="F4LFV/P",
            grid="JN18",
            latitude=48.8,
            longitude=2.3,
            last_seen=now,
            message_count=1,
        )
        async_session.add_all([own, remote])
        await async_session.flush()
        async_session.add(
            ReceivedMessage(
                callsign="F4LFV/P",
                from_callsign="F4LFV/P",
                to_callsign="PE1PUX",
                text="PE1PUX MESSAGE",
                message_type="RX.DIRECTED",
                band="40m",
                snr=-7,
                received_at=now,
            )
        )
        await async_session.commit()

        with patch("js8link.app.local_callsign", "PE1PUX"):
            response = await async_client.get("/api/monitor/graph?minutes=60&band=40m")

        assert response.status_code == 200
        link = response.json()["links"][0]
        assert link["source"] == "F4LFV/P"
        assert link["target"] == "PE1PUX"
        assert link["snr_at_source"] is None
        assert link["snr_at_target"] == -7
        assert link["observations_at_source"] == 0
        assert link["observations_at_target"] == 1

    @pytest.mark.asyncio
    async def test_graph_empty(self, async_client) -> None:
        response = await async_client.get("/api/graph")
        assert response.status_code == 200
        data = response.json()
        assert data["nodes"] == []
        assert data["edges"] == []

    @pytest.mark.asyncio
    async def test_monitor_console_compatibility_endpoints(self, async_client) -> None:
        messages = await async_client.get("/api/monitor/messages")
        spectrum = await async_client.get("/api/monitor/spectrum")
        activity = await async_client.get("/api/monitor/band-activity?minutes=60")
        last_heard = await async_client.get("/api/monitor/last-heard")
        graph = await async_client.get("/api/monitor/graph?minutes=60")

        assert messages.status_code == 200
        assert spectrum.status_code == 200
        assert activity.status_code == 200
        assert last_heard.status_code == 200
        assert graph.status_code == 200
        assert messages.json()["messages"] == []
        assert spectrum.json() == {
            "minimum_offset": 500,
            "maximum_offset": 2500,
            "signals": [],
        }
        assert activity.json()["groups"] == []
        assert last_heard.json()["stations"] == []
        assert graph.json() == {"stations": [], "links": []}

    @pytest.mark.asyncio
    async def test_monitor_messages_recovers_sender_from_legacy_activity(
        self, async_client, async_session: AsyncSession
    ) -> None:
        async_session.add(
            ReceivedMessage(
                sender_source="K8MTM ACK",
                text="K8MTM ACK",
                kind="band_activity",
                delivery_mode="best_effort",
            )
        )
        await async_session.commit()

        response = await async_client.get("/api/monitor/messages")

        assert response.status_code == 200
        assert response.json()["messages"][0]["sender"] == "K8MTM"

    @pytest.mark.asyncio
    async def test_monitor_messages_includes_transmitted_traffic(
        self, async_client, async_session: AsyncSession
    ) -> None:
        async_session.add(
            TransmittedMessage(
                callsign="PA3ABC",
                text="Test transmission",
                status="sent",
                band="40m",
                offset=1500,
                mode="Normal",
            )
        )
        await async_session.commit()

        response = await async_client.get("/api/monitor/messages")

        assert response.status_code == 200
        tx_message = response.json()["messages"][0]
        assert tx_message["direction"] == "tx"
        assert tx_message["recipient"] == "PA3ABC"
        assert tx_message["text"] == "Test transmission"


# ============================================================================
# WebSocket endpoint
# ============================================================================


class TestWebSocket:
    @pytest.mark.asyncio
    async def test_websocket_connect(self, app_with_db, mock_js8call) -> None:
        """Verify that a client can open the /api/events WebSocket and
        exchange a ping/pong."""
        with patch("js8link.app.client", mock_js8call):
            test_client = TestClient(app_with_db)
            with test_client.websocket_connect("/api/events") as websocket:
                websocket.send_text("ping")
                data = websocket.receive_text()
                assert data == "pong"

# ============================================================================
# ARQ send with async client
# ============================================================================


class TestARQSend:
    @pytest.mark.asyncio
    async def test_send_confirmed_creates_protocol_id(self, async_client) -> None:
        """Sending with delivery_mode=confirmed must produce a protocol_id
        and set delivery_status in the response."""
        response = await async_client.post(
            "/api/messages/send",
            json={
                "text": "ARQ test message",
                "delivery_mode": "confirmed",
                "callsign": "K1ABC",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["protocol_id"] is not None
        assert len(data["protocol_id"]) > 0
        assert data["delivery_status"] == "transmitting"
        assert data["delivery_mode"] == "confirmed"


class TestStationQueryResponses:
    @pytest.mark.asyncio
    async def test_snr_reply_updates_station_and_query(self, async_session: AsyncSession) -> None:
        station = Station(callsign="DF7ET", message_count=1)
        async_session.add(station)
        await async_session.flush()
        query = StationQuery(station_id=station.id, query_type="snr", status="pending")
        async_session.add(query)
        await async_session.flush()

        handled = await _handle_query_response(
            async_session,
            "DF7ET",
            "SNR",
            "DF7ET SNR -12 ♢",
            {"DIAL": 7078000, "OFFSET": 1500, "SPEED": 0},
        )
        await async_session.commit()

        assert handled is True
        assert station.last_snr == -12
        assert station.last_snr_query_at is not None
        assert query.status == "responded"
        assert query.snr_value == -12
        assert query.response_text == "DF7ET SNR -12 ♢"

    @pytest.mark.asyncio
    async def test_hearing_reply_stores_stations_and_links(self, async_session: AsyncSession) -> None:
        station = Station(callsign="DF7ET", message_count=1)
        async_session.add(station)
        await async_session.flush()
        query = StationQuery(station_id=station.id, query_type="hearing", status="pending")
        async_session.add(query)
        await async_session.flush()

        handled = await _handle_query_response(
            async_session,
            "DF7ET",
            "HEARING",
            "DF7ET HEARING\nPA3ABC SNR -10\nDL1XYZ SNR -18 ♢",
            {"DIAL": 7078000, "OFFSET": 1200, "SPEED": 1},
        )
        await async_session.commit()

        assert handled is True
        assert query.status == "responded"
        assert query.hearing_data is not None
        heard = await async_session.scalars(select(Station).where(Station.callsign.in_(["PA3ABC", "DL1XYZ"])))
        heard_stations = heard.all()
        assert {item.callsign for item in heard_stations} == {"PA3ABC", "DL1XYZ"}
        assert {item.last_offset for item in heard_stations} == {1200}
        links = (await async_session.scalars(select(StationLink))).all()
        assert len(links) == 2
        assert {link.latest_snr for link in links} == {-10, -18}
