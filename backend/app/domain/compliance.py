from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from math import isfinite

from app.domain.geography import haversine_distance_meters

MIN_DURATION_SECONDS = Decimal("300")
MAX_DISTANCE_METERS = Decimal("500")
DISTANCE_EPSILON_METERS = Decimal("0.000001")
MICROSECONDS_PER_SECOND = 1_000_000
SECONDS_PER_DAY = 86_400


class FindingCode(StrEnum):
    DURATION_TOO_SHORT = "DURATION_TOO_SHORT"
    CHECKIN_TOO_FAR = "CHECKIN_TOO_FAR"
    CHECKOUT_TOO_FAR = "CHECKOUT_TOO_FAR"
    INVALID_TIME_SEQUENCE = "INVALID_TIME_SEQUENCE"


class FindingPhase(StrEnum):
    CHECK_IN = "CHECK_IN"
    CHECK_OUT = "CHECK_OUT"


class FindingUnit(StrEnum):
    SECONDS = "SECONDS"
    METERS = "METERS"


FINDING_MESSAGES: dict[FindingCode, str] = {
    FindingCode.DURATION_TOO_SHORT: "Visit duration is shorter than 5 minutes",
    FindingCode.CHECKIN_TOO_FAR: "Check-in location is more than 500 meters from the hospital",
    FindingCode.CHECKOUT_TOO_FAR: "Check-out location is more than 500 meters from the hospital",
    FindingCode.INVALID_TIME_SEQUENCE: "Check-out time must be later than check-in time",
}


@dataclass(frozen=True, slots=True)
class GeoPoint:
    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        if not isfinite(self.latitude) or not -90 <= self.latitude <= 90:
            raise ValueError("latitude must be a finite number between -90 and 90")
        if not isfinite(self.longitude) or not -180 <= self.longitude <= 180:
            raise ValueError("longitude must be a finite number between -180 and 180")


@dataclass(frozen=True, slots=True)
class VisitComplianceInput:
    check_in_at: datetime
    check_out_at: datetime
    hospital_location: GeoPoint
    check_in_location: GeoPoint
    check_out_location: GeoPoint

    def __post_init__(self) -> None:
        _require_aware_datetime(self.check_in_at, "check_in_at")
        _require_aware_datetime(self.check_out_at, "check_out_at")


@dataclass(frozen=True, slots=True)
class ComplianceFinding:
    code: FindingCode
    message: str
    actual_value: Decimal
    threshold: Decimal
    phase: FindingPhase
    unit: FindingUnit

    @property
    def measured_value(self) -> Decimal:
        """Persistence-design alias for the public actual value."""
        return self.actual_value

    @property
    def threshold_value(self) -> Decimal:
        """Persistence-design alias for the public threshold."""
        return self.threshold


@dataclass(frozen=True, slots=True)
class ComplianceResult:
    duration_seconds: Decimal
    check_in_distance_meters: Decimal
    check_out_distance_meters: Decimal
    findings: tuple[ComplianceFinding, ...]


def evaluate_visit_compliance(data: VisitComplianceInput) -> ComplianceResult:
    """Evaluate a complete visit from supplied facts without I/O or ambient time."""
    duration_seconds = _duration_seconds(data.check_in_at, data.check_out_at)
    check_in_distance = _distance_from_hospital(data.hospital_location, data.check_in_location)
    check_out_distance = _distance_from_hospital(data.hospital_location, data.check_out_location)

    findings: list[ComplianceFinding] = []
    if duration_seconds <= 0:
        findings.append(
            _finding(
                FindingCode.INVALID_TIME_SEQUENCE,
                duration_seconds,
                Decimal("0"),
                FindingPhase.CHECK_OUT,
                FindingUnit.SECONDS,
            )
        )
    elif duration_seconds < MIN_DURATION_SECONDS:
        findings.append(
            _finding(
                FindingCode.DURATION_TOO_SHORT,
                duration_seconds,
                MIN_DURATION_SECONDS,
                FindingPhase.CHECK_OUT,
                FindingUnit.SECONDS,
            )
        )

    distance_limit_with_tolerance = MAX_DISTANCE_METERS + DISTANCE_EPSILON_METERS
    if check_in_distance > distance_limit_with_tolerance:
        findings.append(
            _finding(
                FindingCode.CHECKIN_TOO_FAR,
                check_in_distance,
                MAX_DISTANCE_METERS,
                FindingPhase.CHECK_IN,
                FindingUnit.METERS,
            )
        )
    if check_out_distance > distance_limit_with_tolerance:
        findings.append(
            _finding(
                FindingCode.CHECKOUT_TOO_FAR,
                check_out_distance,
                MAX_DISTANCE_METERS,
                FindingPhase.CHECK_OUT,
                FindingUnit.METERS,
            )
        )

    return ComplianceResult(
        duration_seconds=duration_seconds,
        check_in_distance_meters=check_in_distance,
        check_out_distance_meters=check_out_distance,
        findings=tuple(findings),
    )


def _require_aware_datetime(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone offset")


def _duration_seconds(check_in_at: datetime, check_out_at: datetime) -> Decimal:
    delta = check_out_at - check_in_at
    total_microseconds = (
        delta.days * SECONDS_PER_DAY + delta.seconds
    ) * MICROSECONDS_PER_SECOND + delta.microseconds
    return Decimal(total_microseconds) / Decimal(MICROSECONDS_PER_SECOND)


def _distance_from_hospital(hospital: GeoPoint, visit_location: GeoPoint) -> Decimal:
    distance = haversine_distance_meters(
        hospital.latitude,
        hospital.longitude,
        visit_location.latitude,
        visit_location.longitude,
    )
    return Decimal(str(distance))


def _finding(
    code: FindingCode,
    actual_value: Decimal,
    threshold: Decimal,
    phase: FindingPhase,
    unit: FindingUnit,
) -> ComplianceFinding:
    return ComplianceFinding(
        code=code,
        message=FINDING_MESSAGES[code],
        actual_value=actual_value,
        threshold=threshold,
        phase=phase,
        unit=unit,
    )
