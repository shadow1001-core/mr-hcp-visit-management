from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import NoReturn, TypeVar
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.clock import Clock, SystemClock
from app.db.models import (
    Department,
    Hcp,
    HcpPractice,
    Hospital,
    MedicalRepresentative,
    Product,
    VisitPlan,
)
from app.db.repositories.visit_plans import VisitPlanRepository
from app.domain.compliance import (
    ComplianceResult,
    GeoPoint,
    VisitComplianceInput,
    evaluate_visit_compliance,
)
from app.domain.errors import BusinessError, ErrorDetail
from app.domain.geography import haversine_distance_meters

ReferenceEntity = TypeVar("ReferenceEntity", MedicalRepresentative, Hcp, Hospital, Department)


@dataclass(frozen=True)
class ReferenceResult:
    id: UUID
    code: str
    name: str


@dataclass(frozen=True)
class HcpPracticeResult:
    id: UUID
    hcp: ReferenceResult
    hospital: ReferenceResult
    department: ReferenceResult


@dataclass(frozen=True)
class CreatedVisitPlan:
    id: UUID
    planned_at: datetime
    created_at: datetime
    mr: ReferenceResult
    hcp_practice: HcpPracticeResult
    target_products: list[ReferenceResult]


@dataclass(frozen=True)
class CreateVisitPlanCommand:
    mr_id: UUID
    hcp_id: UUID
    hospital_id: UUID
    department_id: UUID
    planned_at: datetime
    product_ids: list[UUID]


@dataclass(frozen=True)
class CheckInCommand:
    workflow_id: UUID
    latitude: Decimal
    longitude: Decimal


@dataclass(frozen=True)
class CheckOutCommand:
    workflow_id: UUID
    latitude: Decimal
    longitude: Decimal


@dataclass(frozen=True)
class DetailingRecordInput:
    product_id: UUID
    content_summary: str


@dataclass(frozen=True)
class MaterialDistributionInput:
    product_id: UUID | None
    material_code: str
    material_name: str
    quantity: int
    is_compliant: bool


@dataclass(frozen=True)
class UpsertVisitReportCommand:
    workflow_id: UUID
    conversation_summary: str
    hcp_feedback: str
    notes: str | None
    detailing_records: list[DetailingRecordInput]
    material_distributions: list[MaterialDistributionInput]


ComplianceEvaluator = Callable[[VisitComplianceInput], ComplianceResult]


class VisitPlanService:
    def __init__(
        self,
        session: Session,
        clock: Clock | None = None,
        compliance_evaluator: ComplianceEvaluator = evaluate_visit_compliance,
    ) -> None:
        self.session = session
        self.repository = VisitPlanRepository(session)
        self.clock = clock or SystemClock()
        self.compliance_evaluator = compliance_evaluator

    def create(self, request: CreateVisitPlanCommand) -> CreatedVisitPlan:
        with self.session.begin():
            representative = self._require_reference(
                self.repository.get_medical_representative(request.mr_id),
                field="mrId",
                code="MR_NOT_FOUND",
                label="Medical representative",
                value=request.mr_id,
            )
            hcp = self._require_reference(
                self.repository.get_hcp(request.hcp_id),
                field="hcpId",
                code="HCP_NOT_FOUND",
                label="HCP",
                value=request.hcp_id,
            )
            hospital = self._require_reference(
                self.repository.get_hospital(request.hospital_id),
                field="hospitalId",
                code="HOSPITAL_NOT_FOUND",
                label="Hospital",
                value=request.hospital_id,
            )
            department = self._require_reference(
                self.repository.get_department(request.department_id),
                field="departmentId",
                code="DEPARTMENT_NOT_FOUND",
                label="Department",
                value=request.department_id,
            )
            products = self._require_products(request.product_ids)
            practice = self._resolve_active_practice(request, hcp, hospital, department)

            plan = self.repository.create_plan(
                representative=representative,
                hcp=hcp,
                hospital=hospital,
                department=department,
                practice=practice,
                products=products,
                planned_at=request.planned_at.astimezone(UTC),
            )

            return CreatedVisitPlan(
                id=plan.id,
                planned_at=plan.planned_at,
                created_at=plan.created_at,
                mr=self._reference_result(representative),
                hcp_practice=HcpPracticeResult(
                    id=practice.id,
                    hcp=self._reference_result(hcp),
                    hospital=self._reference_result(hospital),
                    department=self._reference_result(department),
                ),
                target_products=[self._reference_result(product) for product in products],
            )

    def list_workflows(
        self,
        *,
        statuses: list[str],
        mr_id: UUID | None,
        hcp_id: UUID | None,
        hospital_id: UUID | None,
        department_id: UUID | None,
        product_id: UUID | None,
        planned_from: datetime | None,
        planned_to: datetime | None,
        check_in_from: datetime | None,
        check_in_to: datetime | None,
        is_abnormal: bool | None,
        page: int,
        page_size: int,
        sort: str,
        order: str,
    ) -> tuple[list[VisitPlan], int]:
        self._validate_range(planned_from, planned_to)
        self._validate_range(check_in_from, check_in_to, prefix="checkIn")
        return self.repository.list_workflows(
            statuses=statuses,
            mr_id=mr_id,
            hcp_id=hcp_id,
            hospital_id=hospital_id,
            department_id=department_id,
            product_id=product_id,
            planned_from=self._utc(planned_from),
            planned_to=self._utc(planned_to),
            check_in_from=self._utc(check_in_from),
            check_in_to=self._utc(check_in_to),
            is_abnormal=is_abnormal,
            page=page,
            page_size=page_size,
            sort=sort,
            order=order,
        )

    def get(self, workflow_id: UUID) -> VisitPlan:
        plan = self.repository.get_workflow(workflow_id)
        if plan is None:
            raise BusinessError(
                code="VISIT_WORKFLOW_NOT_FOUND",
                message="The visit workflow was not found.",
                status_code=404,
                details=[ErrorDetail(field="id", reason="NOT_FOUND", value=workflow_id)],
            )
        return plan

    def check_in(self, request: CheckInCommand) -> VisitPlan:
        try:
            with self.session.begin():
                plan = self.repository.lock_workflow(request.workflow_id)
                if plan is None:
                    raise BusinessError(
                        code="VISIT_NOT_FOUND",
                        message="The visit workflow was not found.",
                        status_code=404,
                        details=[
                            ErrorDetail(field="id", reason="NOT_FOUND", value=request.workflow_id)
                        ],
                    )
                existing_visit = self.repository.find_visit_for_plan(plan.id)
                if existing_visit is not None:
                    code = (
                        "VISIT_ALREADY_CHECKED_IN"
                        if existing_visit.check_out_at is None
                        else "INVALID_VISIT_STATE"
                    )
                    raise BusinessError(
                        code=code,
                        message=(
                            "The visit has already been checked in."
                            if code == "VISIT_ALREADY_CHECKED_IN"
                            else "The completed visit cannot be checked in again."
                        ),
                        status_code=409,
                        details=[ErrorDetail(field="id", reason=code, value=plan.id)],
                    )

                hospital = plan.hcp_practice.hospital_department.hospital
                latitude = request.latitude.quantize(Decimal("0.000001"))
                longitude = request.longitude.quantize(Decimal("0.000001"))
                distance = haversine_distance_meters(
                    float(hospital.latitude),
                    float(hospital.longitude),
                    float(latitude),
                    float(longitude),
                )
                self.repository.create_visit(
                    plan=plan,
                    hospital_latitude=hospital.latitude,
                    hospital_longitude=hospital.longitude,
                    check_in_at=self.clock.now().astimezone(UTC),
                    latitude=latitude,
                    longitude=longitude,
                    distance_meters=Decimal(str(distance)).quantize(Decimal("0.000001")),
                )
                return plan
        except IntegrityError as exc:
            if _constraint_name(exc) != "uq_visits_plan_id":
                raise
            raise BusinessError(
                code="VISIT_ALREADY_CHECKED_IN",
                message="The visit has already been checked in.",
                status_code=409,
                details=[
                    ErrorDetail(
                        field="id", reason="VISIT_ALREADY_CHECKED_IN", value=request.workflow_id
                    )
                ],
            ) from exc

    def check_out(self, request: CheckOutCommand) -> VisitPlan:
        with self.session.begin():
            plan = self.repository.lock_workflow(request.workflow_id)
            if plan is None:
                raise BusinessError(
                    code="VISIT_WORKFLOW_NOT_FOUND",
                    message="The visit workflow was not found.",
                    status_code=404,
                    details=[
                        ErrorDetail(field="id", reason="NOT_FOUND", value=request.workflow_id)
                    ],
                )
            visit = self.repository.find_visit_for_plan(plan.id)
            if visit is None:
                raise BusinessError(
                    code="VISIT_NOT_CHECKED_IN",
                    message="The visit must be checked in before check-out.",
                    status_code=409,
                    details=[
                        ErrorDetail(
                            field="id", reason="VISIT_NOT_CHECKED_IN", value=request.workflow_id
                        )
                    ],
                )
            if visit.check_out_at is not None:
                raise BusinessError(
                    code="VISIT_ALREADY_CHECKED_OUT",
                    message="The visit has already been checked out.",
                    status_code=409,
                    details=[
                        ErrorDetail(
                            field="id",
                            reason="VISIT_ALREADY_CHECKED_OUT",
                            value=request.workflow_id,
                        )
                    ],
                )

            checked_out_at = self.clock.now().astimezone(UTC)
            latitude = request.latitude.quantize(Decimal("0.000001"))
            longitude = request.longitude.quantize(Decimal("0.000001"))
            result = self.compliance_evaluator(
                VisitComplianceInput(
                    check_in_at=visit.check_in_at,
                    check_out_at=checked_out_at,
                    hospital_location=GeoPoint(
                        latitude=float(visit.hospital_latitude_snapshot),
                        longitude=float(visit.hospital_longitude_snapshot),
                    ),
                    check_in_location=GeoPoint(
                        latitude=float(visit.check_in_latitude),
                        longitude=float(visit.check_in_longitude),
                    ),
                    check_out_location=GeoPoint(
                        latitude=float(latitude),
                        longitude=float(longitude),
                    ),
                )
            )
            self.repository.complete_visit(
                visit=visit,
                check_out_at=checked_out_at,
                latitude=latitude,
                longitude=longitude,
                result=result,
            )
            return plan

    def upsert_report(self, request: UpsertVisitReportCommand) -> VisitPlan:
        with self.session.begin():
            plan = self.repository.lock_workflow(request.workflow_id)
            if plan is None:
                raise BusinessError(
                    code="VISIT_WORKFLOW_NOT_FOUND",
                    message="The visit workflow was not found.",
                    status_code=404,
                    details=[
                        ErrorDetail(field="id", reason="NOT_FOUND", value=request.workflow_id)
                    ],
                )
            visit = self.repository.find_visit_for_plan(plan.id)
            if visit is None or visit.check_out_at is None:
                raise BusinessError(
                    code="VISIT_NOT_CHECKED_OUT",
                    message="The visit must be checked out before submitting a report.",
                    status_code=409,
                    details=[
                        ErrorDetail(
                            field="id", reason="VISIT_NOT_CHECKED_OUT", value=request.workflow_id
                        )
                    ],
                )

            detailing_product_ids = [item.product_id for item in request.detailing_records]
            if not detailing_product_ids:
                raise BusinessError(
                    code="DETAILING_RECORDS_REQUIRED",
                    message="At least one detailing product is required.",
                    status_code=422,
                    details=[ErrorDetail(field="detailingRecords", reason="AT_LEAST_ONE_REQUIRED")],
                )
            if len(detailing_product_ids) != len(set(detailing_product_ids)):
                raise BusinessError(
                    code="DUPLICATE_DETAILING_PRODUCT",
                    message="Detailing products must not contain duplicates.",
                    status_code=422,
                    details=[ErrorDetail(field="detailingRecords", reason="DUPLICATE_PRODUCT")],
                )

            invalid_material_indexes = [
                index
                for index, item in enumerate(request.material_distributions)
                if item.quantity < 0
            ]
            if invalid_material_indexes:
                raise BusinessError(
                    code="INVALID_MATERIAL_QUANTITY",
                    message="Material quantity must be a non-negative integer.",
                    status_code=422,
                    details=[
                        ErrorDetail(
                            field=f"materialDistributions.{index}.quantity",
                            reason="MUST_BE_NONNEGATIVE",
                        )
                        for index in invalid_material_indexes
                    ],
                )

            plan_product_ids = self.repository.get_plan_product_ids(plan.id)
            unexpected_detailing_ids = [
                product_id
                for product_id in detailing_product_ids
                if product_id not in plan_product_ids
            ]
            if unexpected_detailing_ids:
                raise BusinessError(
                    code="REPORT_PRODUCT_NOT_IN_PLAN",
                    message="Every detailing product must be a target product of the visit plan.",
                    status_code=422,
                    details=[
                        ErrorDetail(
                            field="detailingRecords.productId",
                            reason="NOT_IN_PLAN",
                            value=product_id,
                        )
                        for product_id in unexpected_detailing_ids
                    ],
                )

            unexpected_material_ids = [
                item.product_id
                for item in request.material_distributions
                if item.product_id is not None and item.product_id not in plan_product_ids
            ]
            if unexpected_material_ids:
                raise BusinessError(
                    code="REPORT_PRODUCT_NOT_IN_VISIT",
                    message="A material references a product outside this visit.",
                    status_code=422,
                    details=[
                        ErrorDetail(
                            field="materialDistributions.productId",
                            reason="NOT_IN_VISIT",
                            value=product_id,
                        )
                        for product_id in unexpected_material_ids
                    ],
                )

            self.repository.replace_report(
                visit=visit,
                conversation_summary=request.conversation_summary,
                hcp_feedback=request.hcp_feedback,
                notes=request.notes,
                submitted_at=self.clock.now().astimezone(UTC),
                detailing_records=[
                    (item.product_id, item.content_summary) for item in request.detailing_records
                ],
                material_distributions=[
                    (
                        item.product_id,
                        item.material_code,
                        item.material_name,
                        item.quantity,
                        item.is_compliant,
                    )
                    for item in request.material_distributions
                ],
            )
            return plan

    @staticmethod
    def _validate_range(
        start: datetime | None, end: datetime | None, *, prefix: str = "planned"
    ) -> None:
        start_field = f"{prefix}From"
        end_field = f"{prefix}To"
        for field, value in ((start_field, start), (end_field, end)):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise BusinessError(
                    code="TIMEZONE_REQUIRED",
                    message=f"{field} must include a timezone.",
                    status_code=422,
                    details=[ErrorDetail(field=field, reason="TIMEZONE_REQUIRED")],
                )
        if start is not None and end is not None and start >= end:
            raise BusinessError(
                code="INVALID_TIME_RANGE",
                message=f"{start_field} must be earlier than {end_field}.",
                status_code=422,
                details=[ErrorDetail(field=start_field, reason=f"NOT_BEFORE_{end_field.upper()}")],
            )

    @staticmethod
    def _utc(value: datetime | None) -> datetime | None:
        return value.astimezone(UTC) if value is not None else None

    def _require_products(self, requested_ids: list[UUID]) -> list[Product]:
        products_by_id = {
            product.id: product for product in self.repository.get_products(requested_ids)
        }
        missing_ids = [
            product_id for product_id in requested_ids if product_id not in products_by_id
        ]
        if missing_ids:
            raise BusinessError(
                code="PRODUCT_NOT_FOUND",
                message="One or more products were not found.",
                status_code=404,
                details=[
                    ErrorDetail(field="productIds", reason="NOT_FOUND", value=product_id)
                    for product_id in missing_ids
                ],
            )
        products = [products_by_id[product_id] for product_id in requested_ids]
        for product in products:
            self._require_active(product, "productIds", product.id)
        return products

    def _resolve_active_practice(
        self,
        request: CreateVisitPlanCommand,
        hcp: Hcp,
        hospital: Hospital,
        department: Department,
    ) -> HcpPractice:
        hospital_department = self.repository.find_hospital_department(hospital.id, department.id)
        if hospital_department is None or not hospital_department.is_active:
            self._raise_practice_mismatch(request)
        practice = self.repository.find_hcp_practice(hcp.id, hospital_department.id)
        if practice is None or not practice.is_active:
            self._raise_practice_mismatch(request)
        return practice

    def _raise_practice_mismatch(self, request: CreateVisitPlanCommand) -> NoReturn:
        raise BusinessError(
            code="HCP_PRACTICE_MISMATCH",
            message="The HCP does not have an active practice in the selected hospital department.",
            status_code=422,
            details=[
                ErrorDetail(field="hcpId", reason="PRACTICE_MISMATCH", value=request.hcp_id),
                ErrorDetail(
                    field="hospitalId", reason="PRACTICE_MISMATCH", value=request.hospital_id
                ),
                ErrorDetail(
                    field="departmentId",
                    reason="PRACTICE_MISMATCH",
                    value=request.department_id,
                ),
            ],
        )

    def _require_reference(
        self,
        entity: ReferenceEntity | None,
        *,
        field: str,
        code: str,
        label: str,
        value: UUID,
    ) -> ReferenceEntity:
        if entity is None:
            raise BusinessError(
                code=code,
                message=f"{label} was not found.",
                status_code=404,
                details=[ErrorDetail(field=field, reason="NOT_FOUND", value=value)],
            )
        self._require_active(entity, field, value)
        return entity

    def _require_active(
        self,
        entity: MedicalRepresentative | Hcp | Hospital | Department | Product,
        field: str,
        value: UUID,
    ) -> None:
        if not entity.is_active:
            raise BusinessError(
                code="REFERENCE_INACTIVE",
                message="A referenced resource is inactive.",
                status_code=422,
                details=[ErrorDetail(field=field, reason="INACTIVE", value=value)],
            )

    @staticmethod
    def _reference_result(
        entity: MedicalRepresentative | Hcp | Hospital | Department | Product,
    ) -> ReferenceResult:
        return ReferenceResult(id=entity.id, code=entity.code, name=entity.name)


def workflow_status(plan: VisitPlan) -> str:
    if plan.visit is None:
        return "PLANNED"
    if plan.visit.check_out_at is None:
        return "CHECKED_IN"
    if plan.visit.report is None:
        return "CHECKED_OUT"
    return "REPORTED"


def allowed_actions(plan: VisitPlan) -> list[str]:
    return {
        "PLANNED": ["CHECK_IN"],
        "CHECKED_IN": ["CHECK_OUT"],
        "CHECKED_OUT": ["SUBMIT_REPORT"],
        "REPORTED": ["UPDATE_REPORT"],
    }[workflow_status(plan)]


def _constraint_name(exc: IntegrityError) -> str | None:
    diagnostic = getattr(exc.orig, "diag", None)
    return getattr(diagnostic, "constraint_name", None)
