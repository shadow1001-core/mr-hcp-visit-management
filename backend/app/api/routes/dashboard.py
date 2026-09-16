from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session
from app.application.services.dashboard import DashboardService
from app.core.config import Settings, get_settings
from app.schemas.dashboard import (
    DashboardProductView,
    MonthlyProductVisitItem,
    MonthlyProductVisitsResponse,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/monthly-visits-by-product", response_model=MonthlyProductVisitsResponse)
def monthly_visits_by_product(
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    month: Annotated[str | None, Query()] = None,
    product_id: Annotated[UUID | None, Query(alias="productId")] = None,
) -> MonthlyProductVisitsResponse:
    result = DashboardService(
        session,
        business_timezone=settings.business_timezone,
    ).monthly_visits_by_product(month, product_id=product_id)
    month_range = result.month_range
    return MonthlyProductVisitsResponse(
        month=month_range.month,
        business_timezone=month_range.business_timezone,
        range_start_utc=month_range.start_utc,
        range_end_utc=month_range.end_utc,
        items=[
            MonthlyProductVisitItem(
                product=DashboardProductView(
                    id=item.product_id,
                    code=item.product_code,
                    name=item.product_name,
                ),
                total_count=item.total_count,
                normal_count=item.normal_count,
                abnormal_count=item.abnormal_count,
                pending_count=item.pending_count,
            )
            for item in result.items
        ],
    )
