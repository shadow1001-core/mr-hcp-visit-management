from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session
from app.application.services.reference_data import ReferenceDataService, ReferenceOption
from app.schemas.reference_data import VisitPlanningReferenceDataResponse
from app.schemas.visit_plan import HcpPracticeView, ReferenceView

router = APIRouter(prefix="/api/reference-data", tags=["reference-data"])


@router.get("/visit-planning", response_model=VisitPlanningReferenceDataResponse)
def get_visit_planning_reference_data(
    session: Annotated[Session, Depends(get_db_session)],
) -> VisitPlanningReferenceDataResponse:
    result = ReferenceDataService(session).visit_planning()
    return VisitPlanningReferenceDataResponse(
        medical_representatives=[_reference(item) for item in result.medical_representatives],
        products=[_reference(item) for item in result.products],
        practices=[
            HcpPracticeView(
                id=practice.id,
                hcp=_reference(practice.hcp),
                hospital=_reference(practice.hospital),
                department=_reference(practice.department),
            )
            for practice in result.practices
        ],
    )


def _reference(item: ReferenceOption) -> ReferenceView:
    return ReferenceView(id=item.id, code=item.code, name=item.name)
