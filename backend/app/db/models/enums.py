from enum import StrEnum


class ComplianceFindingCode(StrEnum):
    DURATION_TOO_SHORT = "DURATION_TOO_SHORT"
    CHECKIN_TOO_FAR = "CHECKIN_TOO_FAR"
    CHECKOUT_TOO_FAR = "CHECKOUT_TOO_FAR"
    INVALID_TIME_SEQUENCE = "INVALID_TIME_SEQUENCE"


class CompliancePhase(StrEnum):
    CHECK_IN = "CHECK_IN"
    CHECK_OUT = "CHECK_OUT"


class ComplianceUnit(StrEnum):
    METERS = "METERS"
    SECONDS = "SECONDS"
