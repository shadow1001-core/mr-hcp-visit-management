from math import atan2, cos, radians, sin, sqrt

EARTH_RADIUS_METERS = 6_371_008.8


def haversine_distance_meters(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    """Return the great-circle distance between two WGS 84 coordinates."""
    latitude_delta = radians(latitude_b - latitude_a)
    longitude_delta_degrees = (longitude_b - longitude_a + 180) % 360 - 180
    longitude_delta = radians(longitude_delta_degrees)
    latitude_a_radians = radians(latitude_a)
    latitude_b_radians = radians(latitude_b)
    haversine = sin(latitude_delta / 2) ** 2 + (
        cos(latitude_a_radians) * cos(latitude_b_radians) * sin(longitude_delta / 2) ** 2
    )
    bounded_haversine = min(1.0, max(0.0, haversine))
    central_angle = 2 * atan2(sqrt(bounded_haversine), sqrt(1 - bounded_haversine))
    return EARTH_RADIUS_METERS * central_angle
