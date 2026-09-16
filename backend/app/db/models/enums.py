from enum import StrEnum


class ComplianceFindingCode(StrEnum):
    CHECK_IN_LOCATION_OUT_OF_RANGE = "CHECK_IN_LOCATION_OUT_OF_RANGE"
    CHECK_OUT_LOCATION_OUT_OF_RANGE = "CHECK_OUT_LOCATION_OUT_OF_RANGE"
    DURATION_TOO_SHORT = "DURATION_TOO_SHORT"


class CompliancePhase(StrEnum):
    CHECK_IN = "CHECK_IN"
    CHECK_OUT = "CHECK_OUT"


class ComplianceUnit(StrEnum):
    METERS = "METERS"
    SECONDS = "SECONDS"
