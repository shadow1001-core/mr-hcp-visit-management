"""Align persisted compliance findings with the domain evaluator.

Revision ID: 20260916_0002
Revises: 29cbc6b430c4
Create Date: 2026-09-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260916_0002"
down_revision: str | None = "29cbc6b430c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_visits_check_out_not_before_check_in"), "visits", type_="check")
    op.drop_constraint(op.f("ck_visits_duration_nonnegative"), "visits", type_="check")

    op.drop_constraint(
        op.f("ck_compliance_findings_code_semantics"),
        "compliance_findings",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_compliance_findings_code_allowed"), "compliance_findings", type_="check"
    )
    op.drop_constraint(
        op.f("ck_compliance_findings_measured_value_nonnegative"),
        "compliance_findings",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_compliance_findings_threshold_value_positive"),
        "compliance_findings",
        type_="check",
    )

    # Preserve any findings created under the initial vocabulary before the
    # stricter replacement constraints are installed.
    op.execute(
        sa.text(
            "UPDATE compliance_findings SET code = 'CHECKIN_TOO_FAR' "
            "WHERE code = 'CHECK_IN_LOCATION_OUT_OF_RANGE'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE compliance_findings SET code = 'CHECKOUT_TOO_FAR' "
            "WHERE code = 'CHECK_OUT_LOCATION_OUT_OF_RANGE'"
        )
    )

    op.create_check_constraint(
        op.f("ck_compliance_findings_code_allowed"),
        "compliance_findings",
        "code IN ('DURATION_TOO_SHORT', 'CHECKIN_TOO_FAR', "
        "'CHECKOUT_TOO_FAR', 'INVALID_TIME_SEQUENCE')",
    )
    op.create_check_constraint(
        op.f("ck_compliance_findings_measured_value_valid"),
        "compliance_findings",
        "code = 'INVALID_TIME_SEQUENCE' OR measured_value >= 0",
    )
    op.create_check_constraint(
        op.f("ck_compliance_findings_threshold_value_valid"),
        "compliance_findings",
        "(code = 'INVALID_TIME_SEQUENCE' AND threshold_value = 0) OR "
        "(code <> 'INVALID_TIME_SEQUENCE' AND threshold_value > 0)",
    )
    op.create_check_constraint(
        op.f("ck_compliance_findings_code_semantics"),
        "compliance_findings",
        "(code = 'CHECKIN_TOO_FAR' AND phase = 'CHECK_IN' "
        "AND unit = 'METERS' AND threshold_value = 500 "
        "AND measured_value > threshold_value) OR "
        "(code = 'CHECKOUT_TOO_FAR' AND phase = 'CHECK_OUT' "
        "AND unit = 'METERS' AND threshold_value = 500 "
        "AND measured_value > threshold_value) OR "
        "(code = 'DURATION_TOO_SHORT' AND phase = 'CHECK_OUT' "
        "AND unit = 'SECONDS' AND threshold_value = 300 "
        "AND measured_value >= 0 AND measured_value < threshold_value) OR "
        "(code = 'INVALID_TIME_SEQUENCE' AND phase = 'CHECK_OUT' "
        "AND unit = 'SECONDS' AND threshold_value = 0 "
        "AND measured_value <= threshold_value)",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_compliance_findings_code_semantics"),
        "compliance_findings",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_compliance_findings_code_allowed"), "compliance_findings", type_="check"
    )
    op.drop_constraint(
        op.f("ck_compliance_findings_measured_value_valid"),
        "compliance_findings",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_compliance_findings_threshold_value_valid"),
        "compliance_findings",
        type_="check",
    )

    # The former schema had no representation for invalid time order. Convert it
    # to its closest legacy duration finding before restoring legacy constraints.
    op.execute(
        sa.text(
            "DELETE FROM compliance_findings AS invalid "
            "USING compliance_findings AS duration "
            "WHERE invalid.visit_id = duration.visit_id "
            "AND invalid.code = 'INVALID_TIME_SEQUENCE' "
            "AND duration.code = 'DURATION_TOO_SHORT'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE compliance_findings "
            "SET code = 'DURATION_TOO_SHORT', measured_value = GREATEST(measured_value, 0), "
            "threshold_value = 300 "
            "WHERE code = 'INVALID_TIME_SEQUENCE'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE compliance_findings SET code = 'CHECK_IN_LOCATION_OUT_OF_RANGE' "
            "WHERE code = 'CHECKIN_TOO_FAR'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE compliance_findings SET code = 'CHECK_OUT_LOCATION_OUT_OF_RANGE' "
            "WHERE code = 'CHECKOUT_TOO_FAR'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE visits SET check_out_at = check_in_at "
            "WHERE check_out_at IS NOT NULL AND check_out_at < check_in_at"
        )
    )

    op.create_check_constraint(
        op.f("ck_compliance_findings_code_allowed"),
        "compliance_findings",
        "code IN ('CHECK_IN_LOCATION_OUT_OF_RANGE', "
        "'CHECK_OUT_LOCATION_OUT_OF_RANGE', 'DURATION_TOO_SHORT')",
    )
    op.create_check_constraint(
        op.f("ck_compliance_findings_measured_value_nonnegative"),
        "compliance_findings",
        "measured_value >= 0",
    )
    op.create_check_constraint(
        op.f("ck_compliance_findings_threshold_value_positive"),
        "compliance_findings",
        "threshold_value > 0",
    )
    op.create_check_constraint(
        op.f("ck_compliance_findings_code_semantics"),
        "compliance_findings",
        "(code = 'CHECK_IN_LOCATION_OUT_OF_RANGE' AND phase = 'CHECK_IN' "
        "AND unit = 'METERS' AND threshold_value = 500 "
        "AND measured_value > threshold_value) OR "
        "(code = 'CHECK_OUT_LOCATION_OUT_OF_RANGE' AND phase = 'CHECK_OUT' "
        "AND unit = 'METERS' AND threshold_value = 500 "
        "AND measured_value > threshold_value) OR "
        "(code = 'DURATION_TOO_SHORT' AND phase = 'CHECK_OUT' "
        "AND unit = 'SECONDS' AND threshold_value = 300 "
        "AND measured_value < threshold_value)",
    )
    op.create_check_constraint(
        op.f("ck_visits_check_out_not_before_check_in"),
        "visits",
        "check_out_at IS NULL OR check_out_at >= check_in_at",
    )
    op.create_check_constraint(
        op.f("ck_visits_duration_nonnegative"),
        "visits",
        "duration_seconds IS NULL OR duration_seconds >= 0",
    )
