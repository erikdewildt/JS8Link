# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
from js8link.domain.js8_protocol import describe_api_message, interpret_air_message


def test_group_heartbeat_is_a_beacon_not_a_reception_report() -> None:
    meaning = interpret_air_message("M0XRS: @HB HEARTBEAT IO83")

    assert meaning.kind == "heartbeat_beacon"
    assert meaning.source == "M0XRS"
    assert meaning.target == "@HB"
    assert meaning.grid == "IO83"
    assert meaning.snr is None
    assert "broadcast a heartbeat" in meaning.interpretation
    assert "received @HB" not in meaning.interpretation


def test_heartbeat_snr_identifies_reporter_receiver_and_target_transmitter() -> None:
    meaning = interpret_air_message("IU2ITE: PE1PUX HEARTBEAT SNR +07")

    assert meaning.kind == "heartbeat_report"
    assert meaning.source == "IU2ITE"
    assert meaning.target == "PE1PUX"
    assert meaning.snr == 7
    assert meaning.interpretation == "IU2ITE reports that it received PE1PUX's heartbeat at +07 dB."


def test_heartbeat_report_can_advertise_a_stored_message() -> None:
    meaning = interpret_air_message("KN4CRD: KM4ACK HEARTBEAT SNR -12 MSG 32 ♢")

    assert meaning.kind == "heartbeat_report"
    assert meaning.message_id == "32"
    assert "stored message 32" in meaning.interpretation


def test_corrupted_heartbeat_snr_is_retained_as_partial_report() -> None:
    meaning = interpret_air_message("IU2ITE: PE1PUX HEARTBEAT SNR ??")

    assert meaning.kind == "heartbeat_report"
    assert meaning.source == "IU2ITE"
    assert meaning.target == "PE1PUX"
    assert meaning.snr is None
    assert "SNR value was not decodable" in meaning.interpretation


def test_structured_fields_win_when_rendered_text_is_fragmented() -> None:
    meaning = interpret_air_message(
        "HEARTBEAT SNR ??",
        {"FROM": "IU2ITE", "TO": "PE1PUX", "CMD": "HEARTBEAT", "SNR": 7},
    )

    assert meaning.kind == "heartbeat_report"
    assert meaning.source == "IU2ITE"
    assert meaning.target == "PE1PUX"
    assert meaning.snr is None


def test_documented_directed_query_is_explained() -> None:
    meaning = interpret_air_message("KJ4CTD: W4CAT SNR? ♢")

    assert meaning.kind == "directed_query"
    assert meaning.command == "SNR?"
    assert meaning.source == "KJ4CTD"
    assert meaning.target == "W4CAT"
    assert "asks W4CAT" in meaning.interpretation


def test_store_and_forward_query_is_explained() -> None:
    meaning = interpret_air_message("KM4ACK: KN4CRD QUERY MSG 32")

    assert meaning.kind == "stored_message_query"
    assert meaning.message_id == "32"
    assert "stored message 32" in meaning.interpretation


def test_api_receive_snr_is_kept_distinct_from_reported_snr() -> None:
    meaning = describe_api_message(
        {
            "type": "RX.ACTIVITY",
            "params": {"SNR": -14, "OFFSET": 707},
            "value": "IU2ITE: PE1PUX HEARTBEAT SNR +07",
        }
    )

    assert meaning.air_message is not None
    assert meaning.air_message.snr == 7
    assert "decoded IU2ITE's transmitted frame at -14 dB" in meaning.interpretation
    assert "distinct from any SNR written inside the message" in meaning.interpretation


def test_documented_outbound_api_command_has_specific_meaning() -> None:
    meaning = describe_api_message(
        {"type": "RIG.SET_FREQ", "params": {"DIAL": 7_078_000, "OFFSET": 1_500}, "value": ""},
        outbound=True,
    )

    assert meaning.summary == "RIG.SET_FREQ sent"
    assert "7078000 Hz" in meaning.interpretation
    assert "1500 Hz" in meaning.interpretation


def test_undocumented_api_type_is_retained_as_unknown() -> None:
    meaning = describe_api_message({"type": "EXPERIMENTAL.VALUE", "params": {}, "value": "x"})

    assert meaning.summary == "Undocumented JS8Call API message"
    assert "preserves the complete envelope" in meaning.interpretation


# ── Partial / corrupted decode handling ────────────────────────────────────


def test_partial_heartbeat_without_snr_is_still_recognised() -> None:
    """A heartbeat report where the SNR value was not decoded."""
    meaning = interpret_air_message("IU2ITE: PE1PUX HEARTBEAT")

    assert meaning.kind == "heartbeat_report"
    assert meaning.source == "IU2ITE"
    assert meaning.target == "PE1PUX"
    assert meaning.snr is None
    assert "heartbeat" in meaning.interpretation.lower()
    assert "not decodable" in meaning.interpretation


def test_partial_short_response_r_maps_to_rr() -> None:
    """JS8Call sometimes decodes 'R' instead of 'RR'."""
    meaning = interpret_air_message("N0CALL: DF7ET R")

    assert meaning.kind == "short_response"
    assert meaning.command == "RR"
    assert meaning.source == "N0CALL"
    assert meaning.target == "DF7ET"
    assert "partial" in meaning.interpretation.lower()


def test_partial_short_response_7_maps_to_73() -> None:
    meaning = interpret_air_message("N0CALL: DF7ET 7")

    assert meaning.kind == "short_response"
    assert meaning.command == "73"


def test_partial_short_response_only_with_target() -> None:
    """A partial short response without a target is not treated as short."""
    meaning = interpret_air_message("R")

    # Without a target we cannot reliably classify this as a directed
    # acknowledgement, so it falls through to free text.
    assert meaning.kind != "short_response"


def test_standalone_cq_is_detected() -> None:
    """'CQ' alone (no trailing space or grid) is a CQ call."""
    meaning = interpret_air_message("N0CALL: CQ")

    assert meaning.kind == "cq"
    assert meaning.source == "N0CALL"


def test_cq_with_corrupted_grid_still_matches() -> None:
    """CQ with a grid that is partially decoded still classifies as CQ."""
    meaning = interpret_air_message("N0CALL: CQ IO9")

    # IO9 is not a valid grid, but the frame is still a CQ call.
    assert meaning.kind == "cq"
    assert meaning.source == "N0CALL"
    assert meaning.grid is None


def test_cq_without_source_colon_uses_first_token_as_cq_source() -> None:
    """Without CALLSIGN: prefix, 'CALLSIGN CQ' infers the caller from position."""
    meaning = interpret_air_message("N0CALL CQ")

    assert meaning.kind == "cq"
    # N0CALL is inferred as the source (the station calling CQ).
    assert meaning.source == "N0CALL"
    assert meaning.target is None


def test_truncated_target_without_body() -> None:
    """A directed frame with only a target callsign and no body text."""
    meaning = interpret_air_message("N0CALL: DF7ET")

    # We can still identify source and target even though the body is empty.
    assert meaning.source == "N0CALL"
    assert meaning.target == "DF7ET"
    # Falls through to directed_message with empty body.
    assert meaning.kind == "directed_message"
    assert meaning.payload == ""


def test_api_message_with_partial_decode_does_not_crash() -> None:
    """describe_api_message must not raise on a structurally incomplete event."""
    meaning = describe_api_message({
        "type": "RX.DIRECTED",
        "params": {"SNR": -5},
        "value": "",
    })

    assert meaning.summary is not None
    assert meaning.air_message is not None
    # Empty value + structured params should still produce a meaning.


def test_params_from_takes_precedence_over_partial_text() -> None:
    """Structured params.FROM is preferred even when text extraction fails."""
    meaning = interpret_air_message(
        "garbled text without proper callsign",
        {"FROM": "DF7ET", "TO": "PE1PUX", "CMD": "HELLO"},
    )

    assert meaning.source == "DF7ET"
    assert meaning.target == "PE1PUX"
