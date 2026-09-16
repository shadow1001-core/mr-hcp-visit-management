from datetime import datetime
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session
from app.api.routes.visit_plans import _plan_response
from app.application.services.visit_plans import (
    CheckInCommand,
    VisitPlanService,
    allowed_actions,
    workflow_status,
)
from app.db.models import Visit, VisitPlan
from app.schemas.visit_plan import (
    ActualVisitView,
    CheckInRequest,
    ComplianceFindingView,
    ExecutionSummaryView,
    PaginatedVisitWorkflows,
    ReferenceView,
    VisitMomentView,
    VisitStatus,
    VisitWorkflowDetail,
    VisitWorkflowSummary,
)

router = APIRouter(prefix="/api/visits", tags=["visits"])


@router.get("", response_model=PaginatedVisitWorkflows)
def list_visits(
    session: Annotated[Session, Depends(get_db_session)],
    status_filter: Annotated[list[VisitStatus] | None, Query(alias="status")] = None,
    mr_id: Annotated[UUID | None, Query(alias="mrId")] = None,
    hcp_id: Annotated[UUID | None, Query(alias="hcpId")] = None,
    hospital_id: Annotated[UUID | None, Query(alias="hospitalId")] = None,
    department_id: Annotated[UUID | None, Query(alias="departmentId")] = None,
    product_id: Annotated[UUID | None, Query(alias="productId")] = None,
    is_abnormal: Annotated[bool | None, Query(alias="isAbnormal")] = None,
    planned_from: Annotated[datetime | None, Query(alias="plannedFrom")] = None,
    planned_to: Annotated[datetime | None, Query(alias="plannedTo")] = None,
    check_in_from: Annotated[datetime | None, Query(alias="checkInFrom")] = None,
    check_in_to: Annotated[datetime | None, Query(alias="checkInTo")] = None,
    sort: Literal["plannedAt", "checkInAt", "createdAt"] = "plannedAt",
    order: Literal["asc", "desc"] = "desc",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
) -> PaginatedVisitWorkflows:
    plans, total = VisitPlanService(session).list_workflows(
        statuses=list(status_filter or []),
        mr_id=mr_id,
        hcp_id=hcp_id,
        hospital_id=hospital_id,
        department_id=department_id,
        product_id=product_id,
        planned_from=planned_from,
        planned_to=planned_to,
        check_in_from=check_in_from,
        check_in_to=check_in_to,
        is_abnormal=is_abnormal,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
    )
    return PaginatedVisitWorkflows(
        items=[_summary(plan) for plan in plans],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/{workflow_id}", response_model=VisitWorkflowDetail)
def get_visit(
    workflow_id: UUID,
    session: Annotated[Session, Depends(get_db_session)],
) -> VisitWorkflowDetail:
    plan = VisitPlanService(session).get(workflow_id)
    return _detail_response(plan)


@router.post("/{workflow_id}/check-in", response_model=VisitWorkflowDetail)
def check_in_visit(
    workflow_id: UUID,
    request: CheckInRequest,
    session: Annotated[Session, Depends(get_db_session)],
) -> VisitWorkflowDetail:
    plan = VisitPlanService(session).check_in(
        CheckInCommand(
            workflow_id=workflow_id,
            latitude=request.latitude,
            longitude=request.longitude,
        )
    )
    return _detail_response(plan)


def _detail_response(plan: VisitPlan) -> VisitWorkflowDetail:
    status = cast(VisitStatus, workflow_status(plan))
    return VisitWorkflowDetail(
        id=plan.id,
        status=status,
        plan=_plan_response(plan),
        actual_visit=_actual_visit(plan.visit) if plan.visit is not None else None,
        report=_report(plan.visit) if status == "REPORTED" and plan.visit is not None else None,
        allowed_actions=cast(
            list[Literal["CHECK_IN", "CHECK_OUT", "SUBMIT_REPORT"]], allowed_actions(plan)
        ),
    )


def _summary(plan: VisitPlan) -> VisitWorkflowSummary:
    visit = plan.visit
    return VisitWorkflowSummary(
        **_plan_response(plan).model_dump(),
        execution_summary=(
            ExecutionSummaryView(
                check_in_at=visit.check_in_at,
                check_out_at=visit.check_out_at,
                duration_seconds=visit.duration_seconds,
                is_abnormal=bool(visit.compliance_findings),
                finding_codes=sorted(finding.code for finding in visit.compliance_findings),
            )
            if visit is not None
            else None
        ),
        report_submitted_at=visit.report.submitted_at if visit and visit.report else None,
    )


def _actual_visit(visit: Visit) -> ActualVisitView:
    findings = sorted(visit.compliance_findings, key=lambda item: (item.detected_at, item.code))
    return ActualVisitView(
        check_in=VisitMomentView(
            at=visit.check_in_at,
            latitude=visit.check_in_latitude,
            longitude=visit.check_in_longitude,
            distance_meters=visit.check_in_distance_meters,
        ),
        check_out=(
            VisitMomentView(
                at=visit.check_out_at,
                latitude=visit.check_out_latitude,
                longitude=visit.check_out_longitude,
                distance_meters=visit.check_out_distance_meters,
            )
            if visit.check_out_at is not None
            and visit.check_out_latitude is not None
            and visit.check_out_longitude is not None
            and visit.check_out_distance_meters is not None
            else None
        ),
        duration_seconds=visit.duration_seconds,
        products=[
            ReferenceView(
                id=product.product_id,
                code=product.product_code_snapshot,
                name=product.product_name_snapshot,
            )
            for product in sorted(visit.products, key=lambda item: item.product_code_snapshot)
        ],
        compliance_status=(
            "ABNORMAL" if findings else "IN_PROGRESS" if visit.check_out_at is None else "NORMAL"
        ),
        compliance_findings=[
            ComplianceFindingView(
                code=finding.code,
                phase=finding.phase,
                measured_value=finding.measured_value,
                threshold_value=finding.threshold_value,
                unit=finding.unit,
                detected_at=finding.detected_at,
            )
            for finding in findings
        ],
    )


def _report(visit: Visit) -> dict[str, object] | None:
    report = visit.report
    if report is None:
        return None
    return {
        "conversationSummary": report.conversation_summary,
        "hcpFeedback": report.hcp_feedback,
        "detailingRecords": [
            {"productId": str(item.product_id), "contentSummary": item.content_summary}
            for item in report.detailing_records
        ],
        "materialDistributions": [
            {
                "id": str(item.id),
                "productId": str(item.product_id) if item.product_id else None,
                "materialCode": item.material_code,
                "materialName": item.material_name,
                "quantity": item.quantity,
                "isCompliant": item.is_compliant,
            }
            for item in report.material_distributions
        ],
        "submittedAt": report.submitted_at,
        "createdAt": report.created_at,
    }
