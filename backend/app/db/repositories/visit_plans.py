from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, and_, case, exists, func, select
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.sql.base import ExecutableOption
from sqlalchemy.sql.elements import ColumnElement

from app.db.models import (
    ComplianceFinding,
    ComplianceFindingCode,
    CompliancePhase,
    ComplianceUnit,
    Department,
    Hcp,
    HcpPractice,
    Hospital,
    HospitalDepartment,
    MedicalRepresentative,
    Product,
    Visit,
    VisitPlan,
    VisitPlanProduct,
    VisitProduct,
    VisitReport,
)
from app.domain.compliance import ComplianceResult

VISIT_STATUS = case(
    (Visit.id.is_(None), "PLANNED"),
    (Visit.check_out_at.is_(None), "CHECKED_IN"),
    (VisitReport.visit_id.is_(None), "CHECKED_OUT"),
    else_="REPORTED",
)


class VisitPlanRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_medical_representative(self, entity_id: UUID) -> MedicalRepresentative | None:
        return self.session.get(MedicalRepresentative, entity_id)

    def get_hcp(self, entity_id: UUID) -> Hcp | None:
        return self.session.get(Hcp, entity_id)

    def get_hospital(self, entity_id: UUID) -> Hospital | None:
        return self.session.get(Hospital, entity_id)

    def get_department(self, entity_id: UUID) -> Department | None:
        return self.session.get(Department, entity_id)

    def get_products(self, entity_ids: Sequence[UUID]) -> list[Product]:
        return list(self.session.scalars(select(Product).where(Product.id.in_(entity_ids))).all())

    def find_hospital_department(
        self, hospital_id: UUID, department_id: UUID
    ) -> HospitalDepartment | None:
        return self.session.scalar(
            select(HospitalDepartment).where(
                HospitalDepartment.hospital_id == hospital_id,
                HospitalDepartment.department_id == department_id,
            )
        )

    def find_hcp_practice(self, hcp_id: UUID, hospital_department_id: UUID) -> HcpPractice | None:
        return self.session.scalar(
            select(HcpPractice).where(
                HcpPractice.hcp_id == hcp_id,
                HcpPractice.hospital_department_id == hospital_department_id,
            )
        )

    def create_plan(
        self,
        *,
        representative: MedicalRepresentative,
        hcp: Hcp,
        hospital: Hospital,
        department: Department,
        practice: HcpPractice,
        products: Sequence[Product],
        planned_at: datetime,
    ) -> VisitPlan:
        plan = VisitPlan(
            medical_representative=representative,
            hcp_practice=practice,
            planned_at=planned_at,
            mr_code_snapshot=representative.code,
            mr_name_snapshot=representative.name,
            hcp_code_snapshot=hcp.code,
            hcp_name_snapshot=hcp.name,
            hospital_code_snapshot=hospital.code,
            hospital_name_snapshot=hospital.name,
            department_code_snapshot=department.code,
            department_name_snapshot=department.name,
        )
        plan.products = [
            VisitPlanProduct(
                product=product,
                product_code_snapshot=product.code,
                product_name_snapshot=product.name,
            )
            for product in products
        ]
        self.session.add(plan)
        self.session.flush()
        return plan

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
        query = self._workflow_base_query()
        conditions: list[ColumnElement[bool]] = []
        if statuses:
            conditions.append(VISIT_STATUS.in_(statuses))
        if mr_id is not None:
            conditions.append(VisitPlan.mr_id == mr_id)
        if hcp_id is not None:
            conditions.append(HcpPractice.hcp_id == hcp_id)
        if hospital_id is not None:
            conditions.append(HospitalDepartment.hospital_id == hospital_id)
        if department_id is not None:
            conditions.append(HospitalDepartment.department_id == department_id)
        if product_id is not None:
            conditions.append(
                exists().where(
                    and_(
                        VisitPlanProduct.plan_id == VisitPlan.id,
                        VisitPlanProduct.product_id == product_id,
                    )
                )
            )
        if planned_from is not None:
            conditions.append(VisitPlan.planned_at >= planned_from)
        if planned_to is not None:
            conditions.append(VisitPlan.planned_at < planned_to)
        if check_in_from is not None:
            conditions.append(Visit.check_in_at >= check_in_from)
        if check_in_to is not None:
            conditions.append(Visit.check_in_at < check_in_to)
        if is_abnormal is not None:
            has_finding = exists().where(ComplianceFinding.visit_id == Visit.id)
            conditions.append(has_finding if is_abnormal else ~has_finding)
            conditions.append(Visit.id.is_not(None))
        query = query.where(*conditions)

        total = self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        sort_column = {
            "plannedAt": VisitPlan.planned_at,
            "createdAt": VisitPlan.created_at,
            "checkInAt": Visit.check_in_at,
        }[sort]
        direction = sort_column.asc() if order == "asc" else sort_column.desc()
        nulls_direction = direction.nullslast() if sort == "checkInAt" else direction
        id_direction = VisitPlan.id.asc() if order == "asc" else VisitPlan.id.desc()
        plan_ids = list(
            self.session.scalars(
                query.with_only_columns(VisitPlan.id)
                .order_by(nulls_direction, id_direction)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        if not plan_ids:
            return [], total
        plans_by_id = {
            plan.id: plan
            for plan in self.session.scalars(
                select(VisitPlan).where(VisitPlan.id.in_(plan_ids)).options(*self._load_options())
            )
            .unique()
            .all()
        }
        return [plans_by_id[plan_id] for plan_id in plan_ids], total

    def get_workflow(self, workflow_id: UUID) -> VisitPlan | None:
        return self.session.scalar(
            select(VisitPlan)
            .where(VisitPlan.id == workflow_id)
            .options(*self._load_options(detail=True))
        )

    def lock_workflow(self, workflow_id: UUID) -> VisitPlan | None:
        return self.session.scalar(
            select(VisitPlan).where(VisitPlan.id == workflow_id).with_for_update()
        )

    def find_visit_for_plan(self, plan_id: UUID) -> Visit | None:
        return self.session.scalar(select(Visit).where(Visit.plan_id == plan_id))

    def create_visit(
        self,
        *,
        plan: VisitPlan,
        hospital_latitude: Decimal,
        hospital_longitude: Decimal,
        check_in_at: datetime,
        latitude: Decimal,
        longitude: Decimal,
        distance_meters: Decimal,
    ) -> Visit:
        plan_products = list(
            self.session.scalars(
                select(VisitPlanProduct).where(VisitPlanProduct.plan_id == plan.id)
            ).all()
        )
        visit = Visit(
            plan=plan,
            hospital_latitude_snapshot=hospital_latitude,
            hospital_longitude_snapshot=hospital_longitude,
            check_in_at=check_in_at,
            check_in_latitude=latitude,
            check_in_longitude=longitude,
            check_in_distance_meters=distance_meters,
            products=[
                VisitProduct(
                    product_id=product.product_id,
                    product_code_snapshot=product.product_code_snapshot,
                    product_name_snapshot=product.product_name_snapshot,
                )
                for product in plan_products
            ],
        )
        self.session.add(visit)
        self.session.flush()
        return visit

    def complete_visit(
        self,
        *,
        visit: Visit,
        check_out_at: datetime,
        latitude: Decimal,
        longitude: Decimal,
        result: ComplianceResult,
    ) -> None:
        six_places = Decimal("0.000001")
        visit.check_out_at = check_out_at
        visit.check_out_latitude = latitude
        visit.check_out_longitude = longitude
        visit.check_out_distance_meters = result.check_out_distance_meters.quantize(six_places)
        visit.compliance_findings = [
            ComplianceFinding(
                code=ComplianceFindingCode(finding.code.value),
                phase=CompliancePhase(finding.phase.value),
                measured_value=finding.actual_value.quantize(six_places),
                threshold_value=finding.threshold.quantize(six_places),
                unit=ComplianceUnit(finding.unit.value),
                detected_at=check_out_at,
            )
            for finding in result.findings
        ]
        self.session.flush()
        self.session.refresh(visit, attribute_names=["duration_seconds", "updated_at"])

    @staticmethod
    def _workflow_base_query() -> Select[tuple[VisitPlan]]:
        return (
            select(VisitPlan)
            .join(HcpPractice, VisitPlan.hcp_practice_id == HcpPractice.id)
            .join(
                HospitalDepartment,
                HcpPractice.hospital_department_id == HospitalDepartment.id,
            )
            .outerjoin(Visit, Visit.plan_id == VisitPlan.id)
            .outerjoin(VisitReport, VisitReport.visit_id == Visit.id)
        )

    @staticmethod
    def _load_options(*, detail: bool = False) -> tuple[ExecutableOption, ...]:
        practice = joinedload(VisitPlan.hcp_practice).joinedload(HcpPractice.hcp)
        hospital_department = joinedload(VisitPlan.hcp_practice).joinedload(
            HcpPractice.hospital_department
        )
        visit = joinedload(VisitPlan.visit)
        options: list[ExecutableOption] = [
            practice,
            hospital_department.joinedload(HospitalDepartment.hospital),
            hospital_department.joinedload(HospitalDepartment.department),
            selectinload(VisitPlan.products),
            visit.joinedload(Visit.report),
            visit.selectinload(Visit.compliance_findings),
        ]
        if detail:
            options.extend(
                [
                    visit.selectinload(Visit.products),
                    visit.joinedload(Visit.report).selectinload(VisitReport.detailing_records),
                    visit.joinedload(Visit.report).selectinload(VisitReport.material_distributions),
                ]
            )
        return tuple(options)
