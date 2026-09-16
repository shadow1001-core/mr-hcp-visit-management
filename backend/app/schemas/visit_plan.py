from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from pydantic.alias_generators import to_camel
from pydantic_core import PydanticCustomError


class CreateVisitPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mrId: UUID
    hcpId: UUID
    hospitalId: UUID
    departmentId: UUID
    plannedAt: datetime
    productIds: list[UUID]

    @field_validator("plannedAt")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise PydanticCustomError("timezone_required", "plannedAt must include a timezone")
        return value

    @field_validator("productIds")
    @classmethod
    def validate_products(cls, value: list[UUID]) -> list[UUID]:
        if not value:
            raise PydanticCustomError("products_required", "At least one product is required")
        if len(value) != len(set(value)):
            raise PydanticCustomError(
                "duplicate_product_id", "productIds must not contain duplicates"
            )
        return value


class CheckInRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latitude: Decimal
    longitude: Decimal

    @field_validator("latitude", "longitude")
    @classmethod
    def validate_coordinates(cls, value: Decimal, info: object) -> Decimal:
        field_name = getattr(info, "field_name", "coordinate")
        lower, upper = (-90, 90) if field_name == "latitude" else (-180, 180)
        if not value.is_finite() or value < lower or value > upper:
            raise PydanticCustomError(
                "invalid_coordinates", f"{field_name} must be between {lower} and {upper}"
            )
        return value


class CheckOutRequest(CheckInRequest):
    pass


NonBlankText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
MaterialCodeText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
MaterialNameText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]


class DetailingRecordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    productId: UUID
    contentSummary: NonBlankText


class MaterialDistributionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    productId: UUID | None = None
    materialCode: MaterialCodeText
    materialName: MaterialNameText
    quantity: Annotated[int, Field(strict=True)]
    isCompliant: bool

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, value: int) -> int:
        if value < 0:
            raise PydanticCustomError(
                "invalid_material_quantity", "quantity must be a non-negative integer"
            )
        return value


class UpsertVisitReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversationSummary: NonBlankText
    hcpFeedback: NonBlankText
    notes: str | None = None
    detailingRecords: list[DetailingRecordRequest]
    materialDistributions: list[MaterialDistributionRequest]

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("detailingRecords")
    @classmethod
    def validate_detailing_records(
        cls, value: list[DetailingRecordRequest]
    ) -> list[DetailingRecordRequest]:
        if not value:
            raise PydanticCustomError(
                "detailing_records_required", "At least one detailing product is required"
            )
        product_ids = [item.productId for item in value]
        if len(product_ids) != len(set(product_ids)):
            raise PydanticCustomError(
                "duplicate_detailing_product", "Detailing products must not contain duplicates"
            )
        return value


class ReferenceView(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: UUID
    code: str
    name: str


class HcpPracticeView(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: UUID
    hcp: ReferenceView
    hospital: ReferenceView
    department: ReferenceView


VisitStatus = Literal["PLANNED", "CHECKED_IN", "CHECKED_OUT", "REPORTED"]


class VisitPlanResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: UUID
    status: VisitStatus = "PLANNED"
    planned_at: datetime
    created_at: datetime
    mr: ReferenceView
    hcp_practice: HcpPracticeView
    target_products: list[ReferenceView]


class PaginatedVisitPlans(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    items: list[VisitPlanResponse]
    page: int
    page_size: int
    total: int


class ExecutionSummaryView(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    check_in_at: datetime
    check_out_at: datetime | None
    duration_seconds: Decimal | None
    is_abnormal: bool
    finding_codes: list[str]


class VisitWorkflowSummary(VisitPlanResponse):
    execution_summary: ExecutionSummaryView | None
    report_submitted_at: datetime | None


class PaginatedVisitWorkflows(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    items: list[VisitWorkflowSummary]
    page: int
    page_size: int
    total: int


class VisitMomentView(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    at: datetime
    latitude: Decimal
    longitude: Decimal
    distance_meters: Decimal


class ComplianceFindingView(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    code: str
    message: str
    actual_value: Decimal
    threshold: Decimal
    phase: str
    unit: str
    detected_at: datetime


class DetailingRecordView(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    product_id: UUID
    content_summary: str


class MaterialDistributionView(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: UUID
    product_id: UUID | None
    material_code: str
    material_name: str
    quantity: int
    is_compliant: bool


class VisitReportView(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    conversation_summary: str
    hcp_feedback: str
    notes: str | None
    detailing_records: list[DetailingRecordView]
    material_distributions: list[MaterialDistributionView]
    submitted_at: datetime
    created_at: datetime


class ActualVisitView(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    check_in: VisitMomentView
    check_out: VisitMomentView | None
    duration_seconds: Decimal | None
    products: list[ReferenceView]
    compliance_status: Literal["IN_PROGRESS", "NORMAL", "ABNORMAL"]
    compliance_findings: list[ComplianceFindingView]


class VisitWorkflowDetail(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: UUID
    status: VisitStatus
    plan: VisitPlanResponse
    actual_visit: ActualVisitView | None
    report: VisitReportView | None
    allowed_actions: list[Literal["CHECK_IN", "CHECK_OUT", "SUBMIT_REPORT", "UPDATE_REPORT"]]
