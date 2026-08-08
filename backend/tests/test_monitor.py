# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
from datetime import UTC, datetime

from js8link.app import _band_activity_entries
from js8link.domain.monitor import (
    classify_received_traffic,
    event_timestamp,
    extract_activity_sender_and_text,
    extract_sender_and_text,
    heartbeat_frame_text,
    is_heartbeat,
    normalize_monitor_text,
    parse_heartbeat_activity,
)


class TestBandActivityEntries:
    def test_expands_js8call_offset_snapshot(self) -> None:
        entries = _band_activity_entries(
            "RX.BAND_ACTIVITY",
            {
                "1067": {
                    "DIAL": 7078000,
                    "OFFSET": 1067,
                    "SNR": -7,
                    "TEXT": "W6OEM: VE3SOY HEARTBEAT SNR -20",
                },
                "616": {
                    "DIAL": 7078000,
                    "OFFSET": 616,
                    "SNR": -18,
                    "TEXT": "KM4BOF: VE3SOY HEARTBEAT SNR -09",
                },
                "_ID": 42,
            },
            "",
        )

        assert [params["OFFSET"] for params, _ in entries] == [1067, 616]
        assert entries[0][1].startswith("W6OEM:")

    def test_keeps_regular_activity_shape(self) -> None:
        entries = _band_activity_entries(
            "RX.ACTIVITY",
            {"OFFSET": 1500, "DIAL": 14074000},
            "CQ N0CALL",
        )

        assert entries == [({"OFFSET": 1500, "DIAL": 14074000}, "CQ N0CALL")]

    def test_skips_scalar_and_offsetless_snapshot_entries(self) -> None:
        entries = _band_activity_entries(
            "RX.BAND_ACTIVITY",
            {
                "_ID": 9,
                "bad": "not an entry",
                "missing-offset": {"TEXT": "N0CALL: CQ"},
                "valid": {"OFFSET": 1200, "TEXT": "N0CALL: CQ"},
            },
            "",
        )

        assert len(entries) == 1
        params, text = entries[0]
        assert params["_ID"] == 9
        assert params["OFFSET"] == 1200
        assert params["TEXT"] == "N0CALL: CQ"
        assert text == "N0CALL: CQ"


class TestExtractSenderAndText:
    def test_heartbeat_frame_text_is_same_for_activity_and_directed_forms(self) -> None:
        assert heartbeat_frame_text("LA7HKA", "SM0OHC", "SM0OHC HEARTBEAT SNR +03") == heartbeat_frame_text(
            "LA7HKA", "SM0OHC", "SM0OHC HEARTBEAT SNR +03 ♢"
        )
        assert heartbeat_frame_text("LA7HKA", "SM0OHC", "SM0OHC HEARTBEAT SNR +03") == (
            "LA7HKA SM0OHC HEARTBEAT SNR +03"
        )

    def test_extracts_sender_from_js8_directed_display_value(self) -> None:
        sender, text = extract_sender_and_text("OZ9JEP: M6AQW HEARTBEAT SNR -15 ♢")
        assert sender == "OZ9JEP"
        assert text == "M6AQW HEARTBEAT SNR -15"

    def test_event_timestamp_invalid_input_falls_back_to_utc(self) -> None:
        timestamp = event_timestamp({"params": {"UTC": "not-a-timestamp"}})

        assert timestamp.tzinfo == UTC

    def test_event_timestamp_accepts_epoch_milliseconds(self) -> None:
        timestamp = event_timestamp({"params": {"UTC": 0}})

        assert timestamp == datetime(1970, 1, 1, tzinfo=UTC)

    def test_does_not_treat_arbitrary_colons_as_callsign_prefixes(self) -> None:
        sender, text = extract_sender_and_text("STATUS: weather is clear")
        assert sender is None
        assert text == "STATUS: weather is clear"

    def test_callsign_with_digits_only_prefix_is_ignored(self) -> None:
        """A callsign must have at least one letter."""
        sender, text = extract_sender_and_text("12345: hello")
        assert sender is None

    def test_callsign_all_letters_is_ignored(self) -> None:
        """A callsign must have at least one digit."""
        sender, text = extract_sender_and_text("ABCDEF: hello")
        assert sender is None

    def test_no_colon_returns_none_sender(self) -> None:
        sender, text = extract_sender_and_text("just some text")
        assert sender is None
        assert text == "just some text"

    def test_empty_input(self) -> None:
        sender, text = extract_sender_and_text("")
        assert sender is None
        assert text == ""

    def test_none_input(self) -> None:
        sender, text = extract_sender_and_text(None)
        assert sender is None
        assert text == ""


class TestExtractActivitySenderAndText:
    def test_extracts_space_separated_band_activity_sender(self) -> None:
        sender, text = extract_activity_sender_and_text("K8MTM ACK")
        assert sender == "K8MTM"
        assert text == "ACK"

    def test_extracts_colon_separated_activity_sender(self) -> None:
        sender, text = extract_activity_sender_and_text("OZ9JEP: M6AQW HEARTBEAT SNR -15 ♢")
        assert sender == "OZ9JEP"
        assert text == "M6AQW HEARTBEAT SNR -15"

    def test_keeps_non_callsign_activity_unknown(self) -> None:
        sender, text = extract_activity_sender_and_text("CQ N0CALL")
        assert sender is None
        assert text == "CQ N0CALL"


class TestNormalizeMonitorText:
    def test_normalizes_display_only_diamond_suffix(self) -> None:
        assert normalize_monitor_text("OZ9JEP: HELLO ♢") == "OZ9JEP: HELLO"
        assert normalize_monitor_text("OZ9JEP: HELLO") == "OZ9JEP: HELLO"

    def test_diamond_only(self) -> None:
        assert normalize_monitor_text("♢") == ""

    def test_diamond_mid_text_not_removed(self) -> None:
        assert normalize_monitor_text("hello ♢ world") == "hello ♢ world"


class TestClassifyReceivedTraffic:
    def test_directed_message(self) -> None:
        assert classify_received_traffic("rx.directed", "MSG") == "direct_message"

    def test_directed_heartbeat(self) -> None:
        assert classify_received_traffic("rx.directed", "HEARTBEAT", heartbeat=True) == "heartbeat"
        assert classify_received_traffic("rx.directed", "HEARTBEAT") == "heartbeat"

    def test_directed_control_commands(self) -> None:
        for cmd in ("ACK", "GRID", "HEARING", "INFO", "QUERY", "SNR", "STATUS"):
            assert classify_received_traffic("rx.directed", cmd) == "directed_control"

    def test_band_activity(self) -> None:
        assert classify_received_traffic("rx.activity") == "band_activity"
        assert classify_received_traffic("rx.band_activity") == "band_activity"

    def test_activity_heartbeat(self) -> None:
        assert classify_received_traffic("rx.activity", heartbeat=True) == "heartbeat"

    def test_unknown_type(self) -> None:
        assert classify_received_traffic("station.status") == "unknown"

    def test_none_type_defaults_to_unknown(self) -> None:
        assert classify_received_traffic(None) == "unknown"

    def test_heartbeat_response_with_msg_command_is_detected_from_value(self) -> None:
        assert (
            is_heartbeat(
                {
                    "type": "RX.DIRECTED",
                    "params": {"CMD": " MSG"},
                    "value": "OZ9JEP: M6AQW HEARTBEAT SNR -15 ♢",
                }
            )
            is True
        )

    def test_case_insensitivity(self) -> None:
        assert classify_received_traffic("RX.DIRECTED", "msg") == "direct_message"


class TestEventTimestamp:
    def test_millisecond_timestamp(self) -> None:
        ts = event_timestamp({"params": {"UTC": 1_700_000_000_000}})
        assert ts.tzinfo == UTC

    def test_iso_string_with_z(self) -> None:
        ts = event_timestamp({"params": {"UTC": "2024-01-15T12:00:00Z"}})
        assert ts.year == 2024
        assert ts.tzinfo == UTC

    def test_iso_string_with_offset(self) -> None:
        ts = event_timestamp({"params": {"UTC": "2024-01-15T12:00:00+00:00"}})
        assert ts.tzinfo == UTC

    def test_iso_string_without_tz_gets_utc(self) -> None:
        ts = event_timestamp({"params": {"UTC": "2024-01-15T12:00:00"}})
        assert ts.tzinfo == UTC

    def test_missing_utc_returns_now(self) -> None:
        before = datetime.now(UTC)
        ts = event_timestamp({"params": {}})
        after = datetime.now(UTC)
        assert before <= ts <= after

    def test_invalid_string_returns_now(self) -> None:
        before = datetime.now(UTC)
        ts = event_timestamp({"params": {"UTC": "not-a-date"}})
        after = datetime.now(UTC)
        assert before <= ts <= after

    def test_no_params_returns_now(self) -> None:
        before = datetime.now(UTC)
        ts = event_timestamp({})
        after = datetime.now(UTC)
        assert before <= ts <= after


class TestIsHeartbeat:
    def test_directed_heartbeat(self) -> None:
        assert is_heartbeat({"type": "RX.DIRECTED", "params": {"CMD": "HEARTBEAT"}}) is True

    def test_directed_not_heartbeat(self) -> None:
        assert is_heartbeat({"type": "RX.DIRECTED", "params": {"CMD": "MSG"}}) is False

    def test_activity_not_heartbeat(self) -> None:
        assert is_heartbeat({"type": "RX.ACTIVITY", "params": {}}) is False

    def test_case_insensitive(self) -> None:
        assert is_heartbeat({"type": "rx.directed", "params": {"CMD": "heartbeat"}}) is True


class TestParseHeartbeatActivity:
    def test_valid_heartbeat_activity(self) -> None:
        result = parse_heartbeat_activity({"type": "RX.ACTIVITY", "value": "PA3ABC: DL1XYZ HEARTBEAT SNR -12"})
        assert result == ("PA3ABC", "DL1XYZ", -12)

    def test_heartbeat_report_first_callsign_is_sender(self) -> None:
        result = parse_heartbeat_activity({"type": "RX.BAND_ACTIVITY", "value": "LA7HKA: DB2ZR HEARTBEAT SNR -04"})
        assert result == ("LA7HKA", "DB2ZR", -4)

    def test_positive_snr(self) -> None:
        result = parse_heartbeat_activity({"type": "RX.BAND_ACTIVITY", "value": "ST1: ST2 HEARTBEAT SNR 5"})
        assert result == ("ST1", "ST2", 5)

    def test_explicit_positive_snr(self) -> None:
        result = parse_heartbeat_activity({"type": "RX.ACTIVITY", "value": "IU2ITE: PE1PUX HEARTBEAT SNR +07"})
        assert result == ("IU2ITE", "PE1PUX", 7)

    def test_group_heartbeat_beacon_is_not_a_report(self) -> None:
        result = parse_heartbeat_activity({"type": "RX.ACTIVITY", "value": "M0XRS: @HB HEARTBEAT IO83"})
        assert result is None

    def test_directed_type_ignored(self) -> None:
        result = parse_heartbeat_activity({"type": "RX.DIRECTED", "value": "PA3ABC: DL1XYZ HEARTBEAT SNR -12"})
        assert result is None

    def test_no_heartbeat_in_text(self) -> None:
        result = parse_heartbeat_activity({"type": "RX.ACTIVITY", "value": "PA3ABC: DL1XYZ CQ"})
        assert result is None
