# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026  JS8Link contributors
from math import radians


def grid_to_coordinates(grid: str) -> tuple[float, float]:
    """Return the center of a Maidenhead locator as latitude/longitude."""
    value = grid.strip().upper()
    if len(value) not in (4, 6):
        raise ValueError("Maidenhead locators must have four or six characters")
    if not ("A" <= value[0] <= "R" and "A" <= value[1] <= "R"):
        raise ValueError("Invalid Maidenhead field")
    lon = (ord(value[0]) - ord("A")) * 20 - 180
    lat = (ord(value[1]) - ord("A")) * 10 - 90
    if not ("0" <= value[2] <= "9" and "0" <= value[3] <= "9"):
        raise ValueError("Invalid Maidenhead square")
    lon += int(value[2]) * 2
    lat += int(value[3])
    lon_width, lat_height = 2.0, 1.0
    if len(value) == 6:
        if not ("A" <= value[4] <= "X" and "A" <= value[5] <= "X"):
            raise ValueError("Invalid Maidenhead subsquare")
        lon_width, lat_height = 2 / 24, 1 / 24
        lon += (ord(value[4]) - ord("A")) * lon_width
        lat += (ord(value[5]) - ord("A")) * lat_height
    return lat + lat_height / 2, lon + lon_width / 2


def try_grid_to_coordinates(grid: str | None) -> tuple[float, float] | None:
    if not grid:
        return None
    try:
        return grid_to_coordinates(grid)
    except ValueError:
        return None


def great_circle_distance_km(source: tuple[float, float], target: tuple[float, float]) -> float:
    from math import asin, cos, sin, sqrt

    lat1, lon1 = map(radians, source)
    lat2, lon2 = map(radians, target)
    delta_lat, delta_lon = lat2 - lat1, lon2 - lon1
    a = sin(delta_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    return 6371.0088 * 2 * asin(sqrt(a))


def initial_bearing_degrees(source: tuple[float, float], target: tuple[float, float]) -> float:
    from math import atan2, cos, degrees, sin

    lat1, lon1 = map(radians, source)
    lat2, lon2 = map(radians, target)
    bearing = atan2(sin(lon2 - lon1) * cos(lat2), cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(lon2 - lon1))
    return (degrees(bearing) + 360) % 360
