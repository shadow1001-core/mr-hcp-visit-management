from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.db.repositories.dashboard import DashboardRepository, MonthlyProductVisitStat
from app.domain.errors import BusinessError, ErrorDetail

MONTH_PATTERN = re.compile(r"^(?P<year>[0-9]{4})-(?P<month>0[1-9]|1[0-2])$")


@dataclass(frozen=True)
class BusinessMonthRange:
    month: str
    business_timezone: str
    start_utc: datetime
    end_utc: datetime


@dataclass(frozen=True)
class MonthlyProductVisits:
    month_range: BusinessMonthRange
    items: list[MonthlyProductVisitStat]


def business_month_utc_range(month: str | None, business_timezone: str) -> BusinessMonthRange:
    normalized_month = month or ""
    match = MONTH_PATTERN.fullmatch(normalized_month)
    if match is None:
        raise _invalid_month(month)

    year = int(match.group("year"))
    month_number = int(match.group("month"))
    timezone = ZoneInfo(business_timezone)
    try:
        start_local = datetime(year, month_number, 1, tzinfo=timezone)
        next_year = year + 1 if month_number == 12 else year
        next_month = 1 if month_number == 12 else month_number + 1
        end_local = datetime(next_year, next_month, 1, tzinfo=timezone)
    except ValueError as exc:
        raise _invalid_month(month) from exc

    return BusinessMonthRange(
        month=normalized_month,
        business_timezone=business_timezone,
        start_utc=start_local.astimezone(UTC),
        end_utc=end_local.astimezone(UTC),
    )


class DashboardService:
    def __init__(self, session: Session, *, business_timezone: str) -> None:
        self.repository = DashboardRepository(session)
        self.business_timezone = business_timezone

    def monthly_visits_by_product(
        self, month: str | None, *, product_id: UUID | None = None
    ) -> MonthlyProductVisits:
        month_range = business_month_utc_range(month, self.business_timezone)
        if product_id is not None and not self.repository.product_exists(product_id):
            raise BusinessError(
                code="REFERENCE_NOT_FOUND",
                message="The product was not found.",
                status_code=404,
                details=[ErrorDetail(field="productId", reason="NOT_FOUND", value=product_id)],
            )
        return MonthlyProductVisits(
            month_range=month_range,
            items=self.repository.monthly_visits_by_product(
                start_utc=month_range.start_utc,
                end_utc=month_range.end_utc,
                product_id=product_id,
            ),
        )


def _invalid_month(month: str | None) -> BusinessError:
    return BusinessError(
        code="INVALID_MONTH",
        message="month must use the YYYY-MM format and identify a valid calendar month.",
        status_code=422,
        details=[ErrorDetail(field="month", reason="INVALID_MONTH", value=month)],
    )
