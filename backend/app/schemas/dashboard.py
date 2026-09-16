from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class DashboardProductView(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: UUID
    code: str
    name: str


class MonthlyProductVisitItem(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    product: DashboardProductView
    total_count: int
    normal_count: int
    abnormal_count: int
    pending_count: int


class MonthlyProductVisitsResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    month: str
    business_timezone: str
    range_start_utc: datetime
    range_end_utc: datetime
    items: list[MonthlyProductVisitItem]
