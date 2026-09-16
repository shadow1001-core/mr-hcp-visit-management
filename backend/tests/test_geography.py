from app.domain.geography import haversine_distance_meters


def test_haversine_distance_is_zero_for_same_coordinate() -> None:
    assert haversine_distance_meters(31.210461, 121.473651, 31.210461, 121.473651) == 0


def test_haversine_distance_is_symmetric() -> None:
    forward = haversine_distance_meters(31.210461, 121.473651, 31.220461, 121.483651)
    reverse = haversine_distance_meters(31.220461, 121.483651, 31.210461, 121.473651)
    assert abs(forward - reverse) < 1e-9
