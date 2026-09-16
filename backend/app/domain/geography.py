from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_METERS = 6_371_000.0


def haversine_distance_meters(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    """Return the great-circle distance between two WGS 84 coordinates."""
    latitude_delta = radians(latitude_b - latitude_a)
    longitude_delta = radians(longitude_b - longitude_a)
    latitude_a_radians = radians(latitude_a)
    latitude_b_radians = radians(latitude_b)
    haversine = sin(latitude_delta / 2) ** 2 + (
        cos(latitude_a_radians) * cos(latitude_b_radians) * sin(longitude_delta / 2) ** 2
    )
    return 2 * EARTH_RADIUS_METERS * asin(sqrt(haversine))
