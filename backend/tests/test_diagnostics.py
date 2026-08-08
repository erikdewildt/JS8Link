# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
import json

from js8link.app import (
    _describe_http_action,
    _describe_js8_message,
    _diagnostic_http_payload,
    _diagnostic_json,
    _diagnostic_summary,
)
from js8link.models import DiagnosticTrace


def test_diagnostic_json_redacts_credentials_and_keeps_raw_context() -> None:
    payload = json.loads(
        _diagnostic_json(
            {
                "type": "STATION.GET_CALLSIGN",
                "params": {"_ID": 7, "TOKEN": "private"},
                "password": "secret",
            }
        )
    )

    assert payload["type"] == "STATION.GET_CALLSIGN"
    assert payload["params"]["_ID"] == 7
    assert payload["params"]["TOKEN"] == "[redacted]"
    assert payload["password"] == "[redacted]"


def test_directed_diagnostic_interpretation_identifies_the_sender() -> None:
    summary, interpretation = _describe_js8_message(
        {"type": "RX.DIRECTED", "params": {"FROM": "PE1PUX"}, "value": "HELLO"},
        False,
    )

    assert summary == "Directed message received"
    assert "PE1PUX" in interpretation
    assert "HELLO" in interpretation


def test_heartbeat_interpretation_explains_reporter_target_and_both_snr_values() -> None:
    summary, interpretation = _describe_js8_message(
        {
            "type": "RX.ACTIVITY",
            "params": {"SNR": -14, "OFFSET": 707},
            "value": "IU2ITE: PE1PUX HEARTBEAT SNR +07",
        },
        False,
    )

    assert summary == "Heartbeat reception report received"
    assert "IU2ITE reports that it received PE1PUX's heartbeat at +07 dB" in interpretation
    assert "decoded IU2ITE's transmitted frame at -14 dB" in interpretation
    assert "distinct from any SNR written inside the message" in interpretation


def test_band_activity_snapshot_interpretation_explains_processing() -> None:
    summary, interpretation = _describe_js8_message(
        {
            "type": "RX.BAND_ACTIVITY",
            "params": {
                "_ID": 42,
                "707": {"OFFSET": 707, "TEXT": "IU2ITE: PE1PUX HEARTBEAT SNR +07"},
            },
            "value": "",
        },
        True,
    )

    assert summary == "Band activity snapshot received"
    assert "1 current band-activity entries" in interpretation
    assert "interpreted independently" in interpretation
    assert "deduplicated before storage" in interpretation


def test_existing_rx_trace_is_reinterpreted_from_its_raw_payload() -> None:
    trace = DiagnosticTrace(
        trace_id="trace-1",
        source="js8_api",
        event_type="RX.ACTIVITY",
        severity="info",
        summary="Band traffic received",
        interpretation="JS8Call decoded RX.ACTIVITY traffic.",
        raw_payload=json.dumps(
            {
                "type": "RX.ACTIVITY",
                "params": {"SNR": -14},
                "value": "IU2ITE: PE1PUX HEARTBEAT SNR +07",
            }
        ),
    )

    result = _diagnostic_summary(trace)

    assert result["summary"] == "Heartbeat reception report received"
    assert "IU2ITE reports that it received PE1PUX's heartbeat at +07 dB" in result["interpretation"]


def test_group_heartbeat_diagnostic_is_not_described_as_receiving_hb_group() -> None:
    summary, interpretation = _describe_js8_message(
        {
            "type": "RX.ACTIVITY",
            "params": {"SNR": -9, "OFFSET": 750},
            "value": "M0XRS: @HB HEARTBEAT IO83",
        },
        False,
    )

    assert summary == "Heartbeat beacon received"
    assert "M0XRS broadcast a heartbeat from locator IO83" in interpretation
    assert "received @HB" not in interpretation


def test_http_diagnostic_interpretation_distinguishes_success_and_failure() -> None:
    assert _describe_http_action("POST", "/api/messages/send", 200)[0] == "Application action completed"
    assert _describe_http_action("GET", "/api/status", 503)[0] == "Application action failed"


def test_http_diagnostic_payload_decodes_json() -> None:
    assert _diagnostic_http_payload(b'{"status":"ok"}', content_type="application/json") == {"status": "ok"}
