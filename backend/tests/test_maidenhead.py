# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
import pytest

from js8link.domain.maidenhead import (
    great_circle_distance_km,
    grid_to_coordinates,
    initial_bearing_degrees,
    try_grid_to_coordinates,
)


class TestGridToCoordinates:
    def test_four_character_grid(self) -> None:
        lat, lon = grid_to_coordinates("JO22")
        assert lat == pytest.approx(52.5)
        assert lon == pytest.approx(5.0)

    def test_six_character_grid(self) -> None:
        lat, lon = grid_to_coordinates("JO22VA")
        assert lat == pytest.approx(52.0208, abs=0.001)
        assert lon == pytest.approx(5.7917, abs=0.001)

    def test_lowercase_input(self) -> None:
        lat, lon = grid_to_coordinates("jo22")
        assert lat == pytest.approx(52.5)

    def test_well_known_locations(self) -> None:
        # JO22: Amsterdam area
        lat, lon = grid_to_coordinates("JO22")
        assert lat == pytest.approx(52.5)
        assert lon == pytest.approx(5.0)

        # FN31: New York area
        lat, lon = grid_to_coordinates("FN31")
        assert lat == pytest.approx(41.5)
        assert lon == pytest.approx(-73.0)

    def test_invalid_length_three_chars(self) -> None:
        with pytest.raises(ValueError, match="four or six"):
            grid_to_coordinates("JO2")

    def test_invalid_length_five_chars(self) -> None:
        with pytest.raises(ValueError, match="four or six"):
            grid_to_coordinates("JO22V")

    def test_invalid_length_seven_chars(self) -> None:
        with pytest.raises(ValueError, match="four or six"):
            grid_to_coordinates("JO22VAA")

    def test_invalid_field_first_letter_too_high(self) -> None:
        with pytest.raises(ValueError, match="Invalid Maidenhead field"):
            grid_to_coordinates("SZ00")  # S > R

    def test_invalid_field_second_letter_too_high(self) -> None:
        with pytest.raises(ValueError, match="Invalid Maidenhead field"):
            grid_to_coordinates("JS00")  # S > R

    def test_invalid_square_digits(self) -> None:
        with pytest.raises(ValueError, match="Invalid Maidenhead square"):
            grid_to_coordinates("JOAB")  # A,B not digits

    def test_invalid_subsquare_letters(self) -> None:
        with pytest.raises(ValueError, match="Invalid Maidenhead subsquare"):
            grid_to_coordinates("JO2200")  # 0,0 are digits, not subsquare letters


class TestTryGridToCoordinates:
    def test_valid_grid_returns_coordinates(self) -> None:
        result = try_grid_to_coordinates("JO22")
        assert result is not None
        assert len(result) == 2

    def test_none_input_returns_none(self) -> None:
        assert try_grid_to_coordinates(None) is None

    def test_empty_string_returns_none(self) -> None:
        assert try_grid_to_coordinates("") is None

    def test_invalid_grid_returns_none(self) -> None:
        assert try_grid_to_coordinates("INVALID") is None


class TestGreatCircleDistance:
    def test_same_point_distance_is_zero(self) -> None:
        ams = (52.3676, 4.9041)
        assert great_circle_distance_km(ams, ams) == pytest.approx(0, abs=0.01)

    def test_amsterdam_berlin(self) -> None:
        ams = (52.3676, 4.9041)
        ber = (52.5200, 13.4050)
        # ~577 km
        dist = great_circle_distance_km(ams, ber)
        assert 570 < dist < 585

    def test_amsterdam_new_york(self) -> None:
        ams = (52.3676, 4.9041)
        nyc = (40.7128, -74.0060)
        # ~5860 km
        dist = great_circle_distance_km(ams, nyc)
        assert 5800 < dist < 5900

    def test_sydney_london(self) -> None:
        syd = (-33.8688, 151.2093)
        ldn = (51.5074, -0.1278)
        # ~16990 km
        dist = great_circle_distance_km(syd, ldn)
        assert 16900 < dist < 17000

    def test_north_pole_to_south_pole(self) -> None:
        npole = (90.0, 0.0)
        spole = (-90.0, 0.0)
        # ~20004 km (half circumference through poles)
        dist = great_circle_distance_km(npole, spole)
        assert 19900 < dist < 20100


class TestInitialBearing:
    def test_due_north(self) -> None:
        bearing = initial_bearing_degrees((50.0, 5.0), (55.0, 5.0))
        assert bearing == pytest.approx(0, abs=0.5)

    def test_due_east(self) -> None:
        bearing = initial_bearing_degrees((50.0, 5.0), (50.0, 15.0))
        assert 85 < bearing < 95

    def test_due_south(self) -> None:
        bearing = initial_bearing_degrees((50.0, 5.0), (45.0, 5.0))
        assert 175 < bearing < 185

    def test_due_west(self) -> None:
        bearing = initial_bearing_degrees((50.0, 5.0), (50.0, -5.0))
        assert 265 < bearing < 275

    def test_bearing_is_normalized_zero_to_360(self) -> None:
        bearing = initial_bearing_degrees((0.0, 0.0), (-1.0, -1.0))
        assert 0 <= bearing < 360
