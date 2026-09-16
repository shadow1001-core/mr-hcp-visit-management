from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UpdatedAtMixin
from app.db.models.enums import ComplianceFindingCode, CompliancePhase, ComplianceUnit


def uuid_primary_key() -> Mapped[UUID]:
    return mapped_column(primary_key=True, default=uuid4)


class MedicalRepresentative(UpdatedAtMixin, Base):
    __tablename__ = "medical_representatives"
    __table_args__ = (
        CheckConstraint("btrim(code) <> ''", name="code_not_blank"),
        CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        Index("idx_medical_representatives_active_name", "is_active", "name"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    visit_plans: Mapped[list[VisitPlan]] = relationship(back_populates="medical_representative")


class Hospital(UpdatedAtMixin, Base):
    __tablename__ = "hospitals"
    __table_args__ = (
        CheckConstraint("btrim(code) <> ''", name="code_not_blank"),
        CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        CheckConstraint("latitude BETWEEN -90 AND 90", name="latitude_range"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="longitude_range"),
        Index("idx_hospitals_active_name", "is_active", "name"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str | None] = mapped_column(String(500))
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    hospital_departments: Mapped[list[HospitalDepartment]] = relationship(back_populates="hospital")


class Department(UpdatedAtMixin, Base):
    __tablename__ = "departments"
    __table_args__ = (
        CheckConstraint("btrim(code) <> ''", name="code_not_blank"),
        CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        Index("idx_departments_active_name", "is_active", "name"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    hospital_departments: Mapped[list[HospitalDepartment]] = relationship(
        back_populates="department"
    )


class HospitalDepartment(UpdatedAtMixin, Base):
    __tablename__ = "hospital_departments"
    __table_args__ = (
        UniqueConstraint(
            "hospital_id", "department_id", name="uq_hospital_departments_hospital_department"
        ),
        CheckConstraint(
            "display_name IS NULL OR btrim(display_name) <> ''", name="display_name_not_blank"
        ),
        Index("idx_hospital_departments_department_id", "department_id"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    hospital_id: Mapped[UUID] = mapped_column(
        ForeignKey("hospitals.id", ondelete="RESTRICT"), nullable=False
    )
    department_id: Mapped[UUID] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False
    )
    display_name: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    hospital: Mapped[Hospital] = relationship(back_populates="hospital_departments")
    department: Mapped[Department] = relationship(back_populates="hospital_departments")
    hcp_practices: Mapped[list[HcpPractice]] = relationship(back_populates="hospital_department")


class Hcp(UpdatedAtMixin, Base):
    __tablename__ = "hcps"
    __table_args__ = (
        CheckConstraint("btrim(code) <> ''", name="code_not_blank"),
        CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        CheckConstraint(
            "professional_title IS NULL OR btrim(professional_title) <> ''",
            name="professional_title_not_blank",
        ),
        Index("idx_hcps_active_name", "is_active", "name"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    professional_title: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    practices: Mapped[list[HcpPractice]] = relationship(back_populates="hcp")


class HcpPractice(UpdatedAtMixin, Base):
    __tablename__ = "hcp_practices"
    __table_args__ = (
        UniqueConstraint(
            "hcp_id", "hospital_department_id", name="uq_hcp_practices_hcp_department"
        ),
        Index("idx_hcp_practices_hospital_department_id", "hospital_department_id"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    hcp_id: Mapped[UUID] = mapped_column(ForeignKey("hcps.id", ondelete="RESTRICT"), nullable=False)
    hospital_department_id: Mapped[UUID] = mapped_column(
        ForeignKey("hospital_departments.id", ondelete="RESTRICT"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    hcp: Mapped[Hcp] = relationship(back_populates="practices")
    hospital_department: Mapped[HospitalDepartment] = relationship(back_populates="hcp_practices")
    visit_plans: Mapped[list[VisitPlan]] = relationship(back_populates="hcp_practice")


class Product(UpdatedAtMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("btrim(code) <> ''", name="code_not_blank"),
        CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        Index("idx_products_active_name", "is_active", "name"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    plan_products: Mapped[list[VisitPlanProduct]] = relationship(back_populates="product")
    visit_products: Mapped[list[VisitProduct]] = relationship(back_populates="product")


class VisitPlan(CreatedAtMixin, Base):
    __tablename__ = "visit_plans"
    __table_args__ = (
        CheckConstraint("btrim(mr_code_snapshot) <> ''", name="mr_code_snapshot_not_blank"),
        CheckConstraint("btrim(mr_name_snapshot) <> ''", name="mr_name_snapshot_not_blank"),
        CheckConstraint("btrim(hcp_code_snapshot) <> ''", name="hcp_code_snapshot_not_blank"),
        CheckConstraint("btrim(hcp_name_snapshot) <> ''", name="hcp_name_snapshot_not_blank"),
        CheckConstraint(
            "btrim(hospital_code_snapshot) <> ''", name="hospital_code_snapshot_not_blank"
        ),
        CheckConstraint(
            "btrim(hospital_name_snapshot) <> ''", name="hospital_name_snapshot_not_blank"
        ),
        CheckConstraint(
            "btrim(department_code_snapshot) <> ''", name="department_code_snapshot_not_blank"
        ),
        CheckConstraint(
            "btrim(department_name_snapshot) <> ''", name="department_name_snapshot_not_blank"
        ),
        Index("idx_visit_plans_mr_planned_at", "mr_id", text("planned_at DESC")),
        Index("idx_visit_plans_hcp_practice_id", "hcp_practice_id"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    mr_id: Mapped[UUID] = mapped_column(
        ForeignKey("medical_representatives.id", ondelete="RESTRICT"), nullable=False
    )
    hcp_practice_id: Mapped[UUID] = mapped_column(
        ForeignKey("hcp_practices.id", ondelete="RESTRICT"), nullable=False
    )
    planned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    mr_code_snapshot: Mapped[str] = mapped_column(String(50), nullable=False)
    mr_name_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)
    hcp_code_snapshot: Mapped[str] = mapped_column(String(50), nullable=False)
    hcp_name_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)
    hospital_code_snapshot: Mapped[str] = mapped_column(String(50), nullable=False)
    hospital_name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    department_code_snapshot: Mapped[str] = mapped_column(String(50), nullable=False)
    department_name_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)

    medical_representative: Mapped[MedicalRepresentative] = relationship(
        back_populates="visit_plans"
    )
    hcp_practice: Mapped[HcpPractice] = relationship(back_populates="visit_plans")
    products: Mapped[list[VisitPlanProduct]] = relationship(back_populates="plan")
    visit: Mapped[Visit | None] = relationship(back_populates="plan", uselist=False)


class VisitPlanProduct(CreatedAtMixin, Base):
    __tablename__ = "visit_plan_products"
    __table_args__ = (
        PrimaryKeyConstraint("plan_id", "product_id", name="pk_visit_plan_products"),
        CheckConstraint(
            "btrim(product_code_snapshot) <> ''", name="product_code_snapshot_not_blank"
        ),
        CheckConstraint(
            "btrim(product_name_snapshot) <> ''", name="product_name_snapshot_not_blank"
        ),
        Index("idx_visit_plan_products_product_plan", "product_id", "plan_id"),
    )

    plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("visit_plans.id", ondelete="RESTRICT"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    product_code_snapshot: Mapped[str] = mapped_column(String(50), nullable=False)
    product_name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)

    plan: Mapped[VisitPlan] = relationship(back_populates="products")
    product: Mapped[Product] = relationship(back_populates="plan_products")


class Visit(UpdatedAtMixin, Base):
    __tablename__ = "visits"
    __table_args__ = (
        UniqueConstraint("plan_id", name="uq_visits_plan_id"),
        CheckConstraint(
            "hospital_latitude_snapshot BETWEEN -90 AND 90",
            name="hospital_latitude_snapshot_range",
        ),
        CheckConstraint(
            "hospital_longitude_snapshot BETWEEN -180 AND 180",
            name="hospital_longitude_snapshot_range",
        ),
        CheckConstraint("check_in_latitude BETWEEN -90 AND 90", name="check_in_latitude_range"),
        CheckConstraint("check_in_longitude BETWEEN -180 AND 180", name="check_in_longitude_range"),
        CheckConstraint(
            "check_out_latitude IS NULL OR check_out_latitude BETWEEN -90 AND 90",
            name="check_out_latitude_range",
        ),
        CheckConstraint(
            "check_out_longitude IS NULL OR check_out_longitude BETWEEN -180 AND 180",
            name="check_out_longitude_range",
        ),
        CheckConstraint("check_in_distance_meters >= 0", name="check_in_distance_nonnegative"),
        CheckConstraint(
            "check_out_distance_meters IS NULL OR check_out_distance_meters >= 0",
            name="check_out_distance_nonnegative",
        ),
        CheckConstraint(
            "(check_out_at IS NULL AND check_out_latitude IS NULL "
            "AND check_out_longitude IS NULL AND check_out_distance_meters IS NULL) OR "
            "(check_out_at IS NOT NULL AND check_out_latitude IS NOT NULL "
            "AND check_out_longitude IS NOT NULL AND check_out_distance_meters IS NOT NULL)",
            name="check_out_fields_complete",
        ),
        CheckConstraint("updated_at >= created_at", name="updated_not_before_created"),
        Index("idx_visits_check_in_at_id", "check_in_at", "id"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("visit_plans.id", ondelete="RESTRICT"), nullable=False
    )
    hospital_latitude_snapshot: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    hospital_longitude_snapshot: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    check_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    check_in_latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    check_in_longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    check_in_distance_meters: Mapped[Decimal] = mapped_column(Numeric(15, 6), nullable=False)
    check_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    check_out_latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    check_out_longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    check_out_distance_meters: Mapped[Decimal | None] = mapped_column(Numeric(15, 6))
    duration_seconds: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6),
        Computed(
            "CASE WHEN check_out_at IS NULL THEN NULL "
            "ELSE EXTRACT(EPOCH FROM (check_out_at - check_in_at)) END",
            persisted=True,
        ),
    )

    plan: Mapped[VisitPlan] = relationship(back_populates="visit")
    products: Mapped[list[VisitProduct]] = relationship(back_populates="visit")
    report: Mapped[VisitReport | None] = relationship(back_populates="visit", uselist=False)
    compliance_findings: Mapped[list[ComplianceFinding]] = relationship(back_populates="visit")


class VisitProduct(CreatedAtMixin, Base):
    __tablename__ = "visit_products"
    __table_args__ = (
        PrimaryKeyConstraint("visit_id", "product_id", name="pk_visit_products"),
        CheckConstraint(
            "btrim(product_code_snapshot) <> ''", name="product_code_snapshot_not_blank"
        ),
        CheckConstraint(
            "btrim(product_name_snapshot) <> ''", name="product_name_snapshot_not_blank"
        ),
        Index("idx_visit_products_product_visit", "product_id", "visit_id"),
    )

    visit_id: Mapped[UUID] = mapped_column(
        ForeignKey("visits.id", ondelete="RESTRICT"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    product_code_snapshot: Mapped[str] = mapped_column(String(50), nullable=False)
    product_name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)

    visit: Mapped[Visit] = relationship(back_populates="products")
    product: Mapped[Product] = relationship(back_populates="visit_products")
    detailing_record: Mapped[AcademicDetailingRecord | None] = relationship(
        back_populates="visit_product", uselist=False, overlaps="detailing_records,report"
    )
    material_distributions: Mapped[list[MaterialDistribution]] = relationship(
        back_populates="visit_product", overlaps="material_distributions,report"
    )


class VisitReport(CreatedAtMixin, Base):
    __tablename__ = "visit_reports"
    __table_args__ = (
        CheckConstraint("btrim(conversation_summary) <> ''", name="conversation_summary_not_blank"),
        CheckConstraint("btrim(hcp_feedback) <> ''", name="hcp_feedback_not_blank"),
    )

    visit_id: Mapped[UUID] = mapped_column(
        ForeignKey("visits.id", ondelete="RESTRICT"), primary_key=True
    )
    conversation_summary: Mapped[str] = mapped_column(Text, nullable=False)
    hcp_feedback: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    visit: Mapped[Visit] = relationship(back_populates="report")
    detailing_records: Mapped[list[AcademicDetailingRecord]] = relationship(
        back_populates="report", overlaps="detailing_record,visit_product"
    )
    material_distributions: Mapped[list[MaterialDistribution]] = relationship(
        back_populates="report", overlaps="material_distributions,visit_product"
    )


class AcademicDetailingRecord(CreatedAtMixin, Base):
    __tablename__ = "academic_detailing_records"
    __table_args__ = (
        PrimaryKeyConstraint("visit_id", "product_id", name="pk_academic_detailing_records"),
        ForeignKeyConstraint(["visit_id"], ["visit_reports.visit_id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["visit_id", "product_id"],
            ["visit_products.visit_id", "visit_products.product_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("btrim(content_summary) <> ''", name="content_summary_not_blank"),
    )

    visit_id: Mapped[UUID] = mapped_column(nullable=False)
    product_id: Mapped[UUID] = mapped_column(nullable=False)
    content_summary: Mapped[str] = mapped_column(Text, nullable=False)

    report: Mapped[VisitReport] = relationship(
        back_populates="detailing_records",
        foreign_keys=[visit_id],
        overlaps="detailing_record,visit_product",
    )
    visit_product: Mapped[VisitProduct] = relationship(
        back_populates="detailing_record",
        foreign_keys=[visit_id, product_id],
        overlaps="detailing_records,report",
    )


class MaterialDistribution(CreatedAtMixin, Base):
    __tablename__ = "material_distributions"
    __table_args__ = (
        ForeignKeyConstraint(["visit_id"], ["visit_reports.visit_id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["visit_id", "product_id"],
            ["visit_products.visit_id", "visit_products.product_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("btrim(material_code) <> ''", name="material_code_not_blank"),
        CheckConstraint("btrim(material_name) <> ''", name="material_name_not_blank"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        Index("idx_material_distributions_visit_id", "visit_id"),
        Index(
            "idx_material_distributions_product_id",
            "product_id",
            postgresql_where=text("product_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = uuid_primary_key()
    visit_id: Mapped[UUID] = mapped_column(nullable=False)
    product_id: Mapped[UUID | None] = mapped_column(nullable=True)
    material_code: Mapped[str] = mapped_column(String(100), nullable=False)
    material_name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    is_compliant: Mapped[bool] = mapped_column(Boolean, nullable=False)

    report: Mapped[VisitReport] = relationship(
        back_populates="material_distributions",
        foreign_keys=[visit_id],
        overlaps="material_distributions,visit_product",
    )
    visit_product: Mapped[VisitProduct | None] = relationship(
        back_populates="material_distributions",
        foreign_keys=[visit_id, product_id],
        overlaps="material_distributions,report",
    )


class ComplianceFinding(CreatedAtMixin, Base):
    __tablename__ = "compliance_findings"
    __table_args__ = (
        UniqueConstraint("visit_id", "code", name="uq_compliance_findings_visit_code"),
        CheckConstraint(
            "code IN ('DURATION_TOO_SHORT', 'CHECKIN_TOO_FAR', "
            "'CHECKOUT_TOO_FAR', 'INVALID_TIME_SEQUENCE')",
            name="code_allowed",
        ),
        CheckConstraint("phase IN ('CHECK_IN', 'CHECK_OUT')", name="phase_allowed"),
        CheckConstraint("unit IN ('METERS', 'SECONDS')", name="unit_allowed"),
        CheckConstraint(
            "code = 'INVALID_TIME_SEQUENCE' OR measured_value >= 0",
            name="measured_value_valid",
        ),
        CheckConstraint(
            "(code = 'INVALID_TIME_SEQUENCE' AND threshold_value = 0) OR "
            "(code <> 'INVALID_TIME_SEQUENCE' AND threshold_value > 0)",
            name="threshold_value_valid",
        ),
        CheckConstraint(
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
            name="code_semantics",
        ),
        Index("idx_compliance_findings_code_detected_at", "code", "detected_at"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    visit_id: Mapped[UUID] = mapped_column(
        ForeignKey("visits.id", ondelete="RESTRICT"), nullable=False
    )
    code: Mapped[ComplianceFindingCode] = mapped_column(String(50), nullable=False)
    phase: Mapped[CompliancePhase] = mapped_column(String(20), nullable=False)
    measured_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    threshold_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit: Mapped[ComplianceUnit] = mapped_column(String(20), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )

    visit: Mapped[Visit] = relationship(back_populates="compliance_findings")
