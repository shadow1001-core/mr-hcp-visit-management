from datetime import datetime
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session
from app.application.services.visit_plans import (
    CreatedVisitPlan,
    CreateVisitPlanCommand,
    VisitPlanService,
    workflow_status,
)
from app.db.models import VisitPlan
from app.schemas.visit_plan import (
    CreateVisitPlanRequest,
    HcpPracticeView,
    PaginatedVisitPlans,
    ReferenceView,
    VisitPlanResponse,
)

router = APIRouter(prefix="/api/visit-plans", tags=["visit-plans"])


@router.get("", response_model=PaginatedVisitPlans)
def list_visit_plans(
    session: Annotated[Session, Depends(get_db_session)],
    status_filter: Annotated[
        list[Literal["PLANNED", "CHECKED_IN", "CHECKED_OUT", "REPORTED"]] | None,
        Query(alias="status"),
    ] = None,
    mr_id: Annotated[UUID | None, Query(alias="mrId")] = None,
    hcp_id: Annotated[UUID | None, Query(alias="hcpId")] = None,
    hospital_id: Annotated[UUID | None, Query(alias="hospitalId")] = None,
    department_id: Annotated[UUID | None, Query(alias="departmentId")] = None,
    product_id: Annotated[UUID | None, Query(alias="productId")] = None,
    planned_from: Annotated[datetime | None, Query(alias="plannedFrom")] = None,
    planned_to: Annotated[datetime | None, Query(alias="plannedTo")] = None,
    sort: Literal["plannedAt", "createdAt"] = "plannedAt",
    order: Literal["asc", "desc"] = "desc",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
) -> PaginatedVisitPlans:
    plans, total = VisitPlanService(session).list_workflows(
        statuses=list(status_filter or []),
        mr_id=mr_id,
        hcp_id=hcp_id,
        hospital_id=hospital_id,
        department_id=department_id,
        product_id=product_id,
        planned_from=planned_from,
        planned_to=planned_to,
        check_in_from=None,
        check_in_to=None,
        is_abnormal=None,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
    )
    return PaginatedVisitPlans(
        items=[_plan_response(plan) for plan in plans],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("", response_model=VisitPlanResponse, status_code=status.HTTP_201_CREATED)
def create_visit_plan(
    request: CreateVisitPlanRequest,
    response: Response,
    session: Annotated[Session, Depends(get_db_session)],
) -> VisitPlanResponse:
    result = VisitPlanService(session).create(
        CreateVisitPlanCommand(
            mr_id=request.mrId,
            hcp_id=request.hcpId,
            hospital_id=request.hospitalId,
            department_id=request.departmentId,
            planned_at=request.plannedAt,
            product_ids=request.productIds,
        )
    )
    response.headers["Location"] = f"/api/visits/{result.id}"
    return _to_response(result)


def _to_response(result: CreatedVisitPlan) -> VisitPlanResponse:
    return VisitPlanResponse(
        id=result.id,
        planned_at=result.planned_at,
        created_at=result.created_at,
        mr=ReferenceView(**vars(result.mr)),
        hcp_practice=HcpPracticeView(
            id=result.hcp_practice.id,
            hcp=ReferenceView(**vars(result.hcp_practice.hcp)),
            hospital=ReferenceView(**vars(result.hcp_practice.hospital)),
            department=ReferenceView(**vars(result.hcp_practice.department)),
        ),
        target_products=[ReferenceView(**vars(product)) for product in result.target_products],
    )


def _plan_response(plan: VisitPlan) -> VisitPlanResponse:
    practice = plan.hcp_practice
    hospital_department = practice.hospital_department
    return VisitPlanResponse(
        id=plan.id,
        status=cast(
            Literal["PLANNED", "CHECKED_IN", "CHECKED_OUT", "REPORTED"], workflow_status(plan)
        ),
        planned_at=plan.planned_at,
        created_at=plan.created_at,
        mr=ReferenceView(id=plan.mr_id, code=plan.mr_code_snapshot, name=plan.mr_name_snapshot),
        hcp_practice=HcpPracticeView(
            id=practice.id,
            hcp=ReferenceView(
                id=practice.hcp_id,
                code=plan.hcp_code_snapshot,
                name=plan.hcp_name_snapshot,
            ),
            hospital=ReferenceView(
                id=hospital_department.hospital_id,
                code=plan.hospital_code_snapshot,
                name=plan.hospital_name_snapshot,
            ),
            department=ReferenceView(
                id=hospital_department.department_id,
                code=plan.department_code_snapshot,
                name=plan.department_name_snapshot,
            ),
        ),
        target_products=[
            ReferenceView(
                id=product.product_id,
                code=product.product_code_snapshot,
                name=product.product_name_snapshot,
            )
            for product in sorted(plan.products, key=lambda item: item.product_code_snapshot)
        ],
    )
