"""Executable contract for docs/compliance-design.md (intentional TDD red phase).

Only the test-side adapter below handles the absent module. Once implemented,
these same cases call the real models and evaluator without changing expectations.
No missing dependency, malformed module, or fixture error is swallowed.
"""

from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal
from importlib import import_module
from importlib.util import find_spec
from math import degrees
from typing import Any

import pytest

MODULE = "app.domain.compliance"
START = datetime.fromisoformat("2026-09-16T10:00:00+08:00")
ORIGIN = (0.0, 0.0)


def north_of_hospital(distance_meters: float) -> tuple[float, float]:
    """Use arc length s=R*theta on one meridian, not a second Haversine implementation.

    Radius is the specification's independent oracle, not a production constant.
    Keep full precision: six-decimal database rounding cannot represent a micrometre
    boundary; these are pure domain tests, not database quantization tests.
    """
    return degrees(distance_meters / 6_371_008.8), 0.0


def contract_module() -> Any:
    if find_spec(MODULE) is None:
        raise NotImplementedError(
            "Compliance feature not implemented: app.domain.compliance.evaluate_visit_compliance"
        )
    return import_module(MODULE)


def evaluate(
    *,
    elapsed: timedelta = timedelta(seconds=300),
    hospital: tuple[float, float] = ORIGIN,
    check_in: tuple[float, float] = ORIGIN,
    check_out: tuple[float, float] = ORIGIN,
    start: datetime = START,
    end: datetime | None = None,
) -> Any:
    module = contract_module()
    data = module.VisitComplianceInput(
        check_in_at=start,
        check_out_at=end if end is not None else start + elapsed,
        hospital_location=module.GeoPoint(latitude=hospital[0], longitude=hospital[1]),
        check_in_location=module.GeoPoint(latitude=check_in[0], longitude=check_in[1]),
        check_out_location=module.GeoPoint(latitude=check_out[0], longitude=check_out[1]),
    )
    before = deepcopy(data)
    result = module.evaluate_visit_compliance(data)
    assert data == before, "Evaluation must not mutate the supplied facts"
    assert isinstance(result.findings, tuple)
    return result


def codes(result: Any) -> tuple[str, ...]:
    return tuple(finding.code for finding in result.findings)


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        pytest.param("299", ("DURATION_TOO_SHORT",), id="four_minutes_59_seconds_is_short"),
        pytest.param("299.999999", ("DURATION_TOO_SHORT",), id="one_microsecond_short"),
        pytest.param("300", (), id="exactly_five_minutes_is_normal"),
        pytest.param("300.000001", (), id="one_microsecond_over_is_normal"),
        pytest.param("301", (), id="five_minutes_one_second_is_normal"),
        pytest.param("-1", ("INVALID_TIME_SEQUENCE",), id="checkout_before_checkin"),
        pytest.param("0", ("INVALID_TIME_SEQUENCE",), id="checkout_equals_checkin"),
    ],
)
def test_duration_rules_and_invalid_sequence_are_mutually_exclusive(
    seconds: str, expected: tuple[str, ...]
) -> None:
    value = Decimal(seconds)
    result = evaluate(elapsed=timedelta(microseconds=int(value * 1_000_000)))
    assert result.duration_seconds == value
    assert isinstance(result.duration_seconds, Decimal)
    assert codes(result) == expected
    if expected:
        finding = result.findings[0]
        assert finding.phase == "CHECK_OUT"
        assert finding.unit == "SECONDS"
        assert finding.measured_value == value
        assert finding.threshold_value == (0 if value <= 0 else 300)


@pytest.mark.parametrize("phase", ["CHECK_IN", "CHECK_OUT"])
@pytest.mark.parametrize(
    ("meters", "too_far"),
    [
        pytest.param(0.0, False, id="same_point_as_hospital"),
        pytest.param(499.0, False, id="499_meters_is_normal"),
        pytest.param(500.0, False, id="exactly_500_meters_is_normal"),
        pytest.param(500.0000005, False, id="within_boundary_epsilon_is_normal"),
        pytest.param(500.000002, True, id="beyond_boundary_epsilon_is_too_far"),
        pytest.param(501.0, True, id="501_meters_is_too_far"),
    ],
)
def test_location_threshold_applies_independently_to_each_phase(
    phase: str, meters: float, too_far: bool
) -> None:
    point = north_of_hospital(meters)
    result = evaluate(
        check_in=point if phase == "CHECK_IN" else ORIGIN,
        check_out=point if phase == "CHECK_OUT" else ORIGIN,
    )
    distance = (
        result.check_in_distance_meters if phase == "CHECK_IN" else result.check_out_distance_meters
    )
    assert isinstance(distance, Decimal)
    # Tighter than the business epsilon; rel=0 prevents a loose relative tolerance.
    assert float(distance) == pytest.approx(meters, rel=0, abs=1e-7)
    expected = "CHECKIN_TOO_FAR" if phase == "CHECK_IN" else "CHECKOUT_TOO_FAR"
    assert codes(result) == ((expected,) if too_far else ())
    if too_far:
        finding = result.findings[0]
        assert finding.phase == phase
        assert finding.unit == "METERS"
        assert finding.threshold_value == Decimal("500")
        assert finding.measured_value == distance


@pytest.mark.parametrize(
    ("seconds", "in_meters", "out_meters", "expected"),
    [
        pytest.param(
            300, 600, 700, ("CHECKIN_TOO_FAR", "CHECKOUT_TOO_FAR"), id="both_locations_are_reported"
        ),
        pytest.param(
            299,
            600,
            0,
            ("DURATION_TOO_SHORT", "CHECKIN_TOO_FAR"),
            id="short_visit_and_checkin_distance",
        ),
        pytest.param(
            299,
            0,
            700,
            ("DURATION_TOO_SHORT", "CHECKOUT_TOO_FAR"),
            id="short_visit_and_checkout_distance",
        ),
        pytest.param(
            299,
            600,
            700,
            ("DURATION_TOO_SHORT", "CHECKIN_TOO_FAR", "CHECKOUT_TOO_FAR"),
            id="all_three_findings_in_stable_order",
        ),
        pytest.param(
            -1,
            600,
            700,
            ("INVALID_TIME_SEQUENCE", "CHECKIN_TOO_FAR", "CHECKOUT_TOO_FAR"),
            id="reversed_time_still_checks_both_locations",
        ),
        pytest.param(
            0,
            600,
            700,
            ("INVALID_TIME_SEQUENCE", "CHECKIN_TOO_FAR", "CHECKOUT_TOO_FAR"),
            id="equal_times_still_check_both_locations",
        ),
    ],
)
def test_all_independent_findings_are_returned_once_in_stable_order(
    seconds: int, in_meters: float, out_meters: float, expected: tuple[str, ...]
) -> None:
    result = evaluate(
        elapsed=timedelta(seconds=seconds),
        check_in=north_of_hospital(in_meters),
        check_out=north_of_hospital(out_meters),
    )
    assert codes(result) == expected


@pytest.mark.parametrize(
    ("start", "end"),
    [
        pytest.param(
            "2026-09-16T23:58:00+08:00",
            "2026-09-17T00:03:00+08:00",
            id="legal_visit_across_midnight",
        ),
        pytest.param(
            "2026-09-16T10:00:00+08:00",
            "2026-09-16T02:05:00+00:00",
            id="different_offsets_represent_five_elapsed_minutes",
        ),
    ],
)
def test_elapsed_time_uses_instants_not_calendar_dates(start: str, end: str) -> None:
    result = evaluate(start=datetime.fromisoformat(start), end=datetime.fromisoformat(end))
    assert result.duration_seconds == Decimal("300")
    assert codes(result) == ()


@pytest.mark.parametrize("point", [(-90.0, -180.0), (90.0, 180.0), (-90.0, 180.0), (90.0, -180.0)])
def test_coordinate_endpoints_are_legal_when_visit_is_at_hospital(
    point: tuple[float, float],
) -> None:
    result = evaluate(hospital=point, check_in=point, check_out=point)
    assert result.check_in_distance_meters == 0
    assert result.check_out_distance_meters == 0
    assert codes(result) == ()


def test_opposite_longitude_labels_at_dateline_mean_same_location() -> None:
    result = evaluate(hospital=(0, 180), check_in=(0, -180), check_out=(0, -180))
    assert float(result.check_in_distance_meters) == pytest.approx(0, abs=1e-7)
    assert float(result.check_out_distance_meters) == pytest.approx(0, abs=1e-7)
    assert codes(result) == ()


@pytest.mark.parametrize("field", ["hospital", "check_in", "check_out"])
@pytest.mark.parametrize(
    "point",
    [
        (90.000001, 0),
        (-90.000001, 0),
        (0, 180.000001),
        (0, -180.000001),
        (float("nan"), 0),
        (0, float("nan")),
        (float("inf"), 0),
        (0, float("-inf")),
    ],
)
def test_invalid_coordinate_is_input_error_not_compliance_finding(
    field: str, point: tuple[float, float]
) -> None:
    # The forthcoming domain input exception must derive from ValueError.
    # NotImplementedError cannot satisfy this expectation accidentally.
    with pytest.raises(ValueError):
        evaluate(
            hospital=point if field == "hospital" else ORIGIN,
            check_in=point if field == "check_in" else ORIGIN,
            check_out=point if field == "check_out" else ORIGIN,
        )


@pytest.mark.parametrize("field", ["start", "end"])
def test_timezone_is_required_for_both_event_times(field: str) -> None:
    with pytest.raises(ValueError):
        evaluate(
            start=datetime(2026, 9, 16, 10) if field == "start" else START,
            end=datetime(2026, 9, 16, 10) if field == "end" else START + timedelta(seconds=300),
        )


def test_repeated_evaluation_of_fixed_facts_is_identical() -> None:
    first = evaluate(
        elapsed=timedelta(seconds=299),
        check_in=north_of_hospital(600),
        check_out=north_of_hospital(700),
    )
    second = evaluate(
        elapsed=timedelta(seconds=299),
        check_in=north_of_hospital(600),
        check_out=north_of_hospital(700),
    )
    assert first == second
