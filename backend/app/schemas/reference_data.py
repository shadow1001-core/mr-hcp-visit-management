from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.schemas.visit_plan import HcpPracticeView, ReferenceView


class VisitPlanningReferenceDataResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    medical_representatives: list[ReferenceView]
    products: list[ReferenceView]
    practices: list[HcpPracticeView]
