# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
from js8link.domain.queries import infer_query_command, parse_query_response, query_spacing_seconds


def test_query_budget_is_spread_over_the_hour() -> None:
    assert query_spacing_seconds(12, 120) == 300
    assert query_spacing_seconds(6, 120) == 600


def test_query_cooldown_remains_a_safety_floor() -> None:
    assert query_spacing_seconds(60, 120) == 120


def test_non_positive_budget_falls_back_to_hourly_spacing() -> None:
    assert query_spacing_seconds(0, 120) == 3600


def test_query_reply_is_inferred_when_js8call_reports_msg_command() -> None:
    assert infer_query_command("MSG", "DF7ET SNR -12 ♢") == "SNR"
    assert infer_query_command("MSG", "DF7ET GRID JO22AB") == "GRID"
    assert infer_query_command("MSG", "ordinary text") is None


def test_query_response_parser_accepts_compact_snr_and_grid_forms() -> None:
    snr = parse_query_response("SNR", "DF7ET SNR -12 ♢")
    grid = parse_query_response("GRID", "JO22AB ♢")

    assert snr is not None and snr.snr == -12
    assert grid is not None and grid.grid == "JO22AB"


def test_query_response_parser_accepts_explicit_positive_snr() -> None:
    response = parse_query_response("SNR", "DF7ET SNR +07 ♢")

    assert response is not None
    assert response.snr == 7


def test_query_response_parser_rejects_partial_numeric_snr() -> None:
    assert parse_query_response("SNR", "SNR +") is None


def test_query_response_parser_keeps_info_and_status_as_text() -> None:
    info = parse_query_response("INFO", "DF7ET INFO Erik, Apeldoorn ♢")
    status = parse_query_response("STATUS", "STATUS Monitoring 40m")

    assert info is not None and info.text == "Erik, Apeldoorn"
    assert status is not None and status.text == "Monitoring 40m"


def test_query_response_parser_extracts_all_hearing_entries() -> None:
    response = parse_query_response(
        "HEARING",
        "DF7ET HEARING\nPA3ABC SNR -10\nDL1XYZ SNR -18 ♢",
    )

    assert response is not None
    assert response.hearing == (
        {"callsign": "PA3ABC", "snr": -10},
        {"callsign": "DL1XYZ", "snr": -18},
    )


# ── Partial / corrupted query responses ────────────────────────────────────


def test_infer_bare_snr_value_without_label() -> None:
    """A bare signed integer without the SNR label is still recognised."""
    assert infer_query_command("MSG", "-12") == "SNR"
    assert infer_query_command("MSG", "+05") == "SNR"


def test_infer_bare_grid_without_label() -> None:
    """A bare 4-char Maidenhead locator without GRID label is recognised."""
    assert infer_query_command("MSG", "JO22") == "GRID"


def test_infer_bare_6char_grid() -> None:
    assert infer_query_command("MSG", "JO22AB") == "GRID"


def test_infer_does_not_confuse_free_text_with_snr() -> None:
    """Free text that happens to look like a number but is too long."""
    assert infer_query_command("MSG", "123") is None
    assert infer_query_command("MSG", "hello world") is None


def test_hearing_response_without_snr_still_extracts_callsigns() -> None:
    """When SNR values are corrupted, at least collect the callsigns."""
    response = parse_query_response("HEARING", "PA3ABC DL1XYZ")

    assert response is not None
    assert len(response.hearing) == 2
    assert response.hearing[0]["callsign"] == "PA3ABC"
    assert response.hearing[1]["callsign"] == "DL1XYZ"
    # SNR defaults to 0 when not decodable.
    assert response.hearing[0]["snr"] == 0


def test_hearing_response_filters_the_label_word_itself() -> None:
    """The word 'HEARING' is never treated as a callsign."""
    response = parse_query_response("HEARING", "HEARING PA3ABC")

    assert response is not None
    assert len(response.hearing) == 1
    assert response.hearing[0]["callsign"] == "PA3ABC"


def test_query_response_with_empty_body_returns_none() -> None:
    """A completely empty response body is handled safely."""
    assert parse_query_response("SNR", "") is None
    assert parse_query_response("GRID", "   ") is None
    assert parse_query_response("HEARING", "") is None


def test_query_response_parser_extracts_store_and_forward_message_ids() -> None:
    response = parse_query_response("MSGS", "MSG 32 MSG 105 ♢")

    assert response is not None
    assert response.msg_ids == (32, 105)
