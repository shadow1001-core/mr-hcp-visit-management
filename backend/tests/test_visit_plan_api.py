from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from math import degrees
from threading import Barrier
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_clock, get_compliance_evaluator, get_db_session
from app.application.services.visit_plans import CreateVisitPlanCommand, VisitPlanService
from app.db.models import (
    AcademicDetailingRecord,
    ComplianceFinding,
    ComplianceFindingCode,
    CompliancePhase,
    ComplianceUnit,
    Department,
    Hcp,
    HcpPractice,
    Hospital,
    MaterialDistribution,
    MedicalRepresentative,
    Product,
    Visit,
    VisitPlan,
    VisitPlanProduct,
    VisitProduct,
    VisitReport,
)
from app.db.repositories.visit_plans import VisitPlanRepository
from app.db.seed import seed_reference_data
from app.domain.compliance import ComplianceResult, VisitComplianceInput
from app.main import app

pytestmark = pytest.mark.integration


@dataclass(frozen=True)
class ApiTestContext:
    client: TestClient
    ids: dict[str, UUID]
    connection_session: Session


@dataclass(frozen=True)
class FixedClock:
    current: datetime

    def now(self) -> datetime:
        return self.current


@pytest.fixture
def api_context(migrated_engine: Engine) -> Iterator[ApiTestContext]:
    connection = migrated_engine.connect()
    outer_transaction = connection.begin()
    setup_session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    with setup_session.begin():
        seed_reference_data(setup_session)

    ids = {
        "mr": _id_by_code(setup_session, MedicalRepresentative, "MR-SH-001"),
        "hcp_ruijin_card": _id_by_code(setup_session, Hcp, "HCP-SH-001"),
        "hcp_zhongshan_card": _id_by_code(setup_session, Hcp, "HCP-SH-003"),
        "hospital_ruijin": _id_by_code(setup_session, Hospital, "HOSP-SH-RJ"),
        "hospital_zhongshan": _id_by_code(setup_session, Hospital, "HOSP-SH-ZS"),
        "department_card": _id_by_code(setup_session, Department, "DEPT-CARD"),
        "department_endo": _id_by_code(setup_session, Department, "DEPT-ENDO"),
        "product_card_a": _id_by_code(setup_session, Product, "PROD-CARD-001"),
        "product_meta_b": _id_by_code(setup_session, Product, "PROD-META-001"),
        "product_card_c": _id_by_code(setup_session, Product, "PROD-CARD-002"),
    }
    setup_session.close()

    def override_session() -> Iterator[Session]:
        with Session(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        ) as request_session:
            yield request_session

    app.dependency_overrides[get_db_session] = override_session
    query_session = Session(bind=connection, expire_on_commit=False)
    try:
        with TestClient(app) as client:
            yield ApiTestContext(client=client, ids=ids, connection_session=query_session)
    finally:
        app.dependency_overrides.clear()
        query_session.close()
        outer_transaction.rollback()
        connection.close()


def _id_by_code(session: Session, model: Any, code: str) -> UUID:
    entity_id = session.scalar(select(model.id).where(model.code == code))
    assert isinstance(entity_id, UUID)
    return entity_id


def _valid_payload(context: ApiTestContext) -> dict[str, Any]:
    return {
        "mrId": str(context.ids["mr"]),
        "hcpId": str(context.ids["hcp_ruijin_card"]),
        "hospitalId": str(context.ids["hospital_ruijin"]),
        "departmentId": str(context.ids["department_card"]),
        "plannedAt": "2026-09-21T09:30:00+08:00",
        "productIds": [
            str(context.ids["product_card_a"]),
            str(context.ids["product_meta_b"]),
        ],
    }


class _ConstraintDiagnostic:
    def __init__(self, constraint_name: str) -> None:
        self.constraint_name = constraint_name


class _ConstraintViolation(Exception):
    def __init__(self, constraint_name: str) -> None:
        self.diag = _ConstraintDiagnostic(constraint_name)


def _integrity_error(constraint_name: str) -> IntegrityError:
    return IntegrityError("test statement", {}, _ConstraintViolation(constraint_name))


def test_visit_planning_reference_data_returns_active_linked_options(
    api_context: ApiTestContext,
) -> None:
    response = api_context.client.get("/api/reference-data/visit-planning")

    assert response.status_code == 200
    body = response.json()
    assert [item["code"] for item in body["medicalRepresentatives"]] == ["MR-SH-001"]
    assert {item["code"] for item in body["products"]} == {
        "PROD-CARD-001",
        "PROD-CARD-002",
        "PROD-META-001",
    }
    assert {
        (
            item["hospital"]["code"],
            item["department"]["code"],
            item["hcp"]["code"],
        )
        for item in body["practices"]
    } == {
        ("HOSP-SH-RJ", "DEPT-CARD", "HCP-SH-001"),
        ("HOSP-SH-RJ", "DEPT-ENDO", "HCP-SH-002"),
        ("HOSP-SH-ZS", "DEPT-CARD", "HCP-SH-003"),
    }


def test_visit_planning_reference_data_excludes_inactive_options(
    api_context: ApiTestContext,
) -> None:
    session = api_context.connection_session
    session.execute(
        update(Product)
        .where(Product.id == api_context.ids["product_card_a"])
        .values(is_active=False)
    )
    session.execute(
        update(HcpPractice)
        .where(HcpPractice.hcp_id == api_context.ids["hcp_ruijin_card"])
        .values(is_active=False)
    )
    session.flush()

    response = api_context.client.get("/api/reference-data/visit-planning")

    assert response.status_code == 200
    body = response.json()
    assert "PROD-CARD-001" not in {item["code"] for item in body["products"]}
    assert "HCP-SH-001" not in {item["hcp"]["code"] for item in body["practices"]}


def test_create_visit_plan_writes_snapshots_and_no_actual_visit(
    api_context: ApiTestContext,
) -> None:
    response = api_context.client.post("/api/visit-plans", json=_valid_payload(api_context))

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "PLANNED"
    assert response.headers["location"] == f"/api/visits/{body['id']}"
    assert body["plannedAt"] == "2026-09-21T01:30:00Z"
    assert body["mr"]["code"] == "MR-SH-001"
    assert body["hcpPractice"]["hcp"]["code"] == "HCP-SH-001"
    assert body["hcpPractice"]["hospital"]["code"] == "HOSP-SH-RJ"
    assert body["hcpPractice"]["department"]["code"] == "DEPT-CARD"
    assert [product["code"] for product in body["targetProducts"]] == [
        "PROD-CARD-001",
        "PROD-META-001",
    ]

    session = api_context.connection_session
    plan = session.get(VisitPlan, UUID(body["id"]))
    assert plan is not None
    assert plan.mr_code_snapshot == "MR-SH-001"
    assert plan.hcp_code_snapshot == "HCP-SH-001"
    assert plan.hospital_code_snapshot == "HOSP-SH-RJ"
    assert plan.department_code_snapshot == "DEPT-CARD"
    assert session.scalar(select(func.count()).select_from(VisitPlanProduct)) == 2
    assert session.scalar(select(func.count()).select_from(Visit)) == 0


@pytest.mark.parametrize(
    ("field", "expected_code"),
    [
        ("mrId", "MR_NOT_FOUND"),
        ("hcpId", "HCP_NOT_FOUND"),
        ("hospitalId", "HOSPITAL_NOT_FOUND"),
        ("departmentId", "DEPARTMENT_NOT_FOUND"),
    ],
)
def test_create_visit_plan_reports_missing_reference(
    api_context: ApiTestContext, field: str, expected_code: str
) -> None:
    payload = _valid_payload(api_context)
    payload[field] = str(uuid4())

    response = api_context.client.post("/api/visit-plans", json=payload)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == expected_code
    assert response.json()["error"]["details"][0]["field"] == field
    assert api_context.connection_session.scalar(select(func.count()).select_from(VisitPlan)) == 0


def test_create_visit_plan_reports_missing_product(api_context: ApiTestContext) -> None:
    payload = _valid_payload(api_context)
    first_missing_id = uuid4()
    second_missing_id = uuid4()
    payload["productIds"] = [
        str(first_missing_id),
        str(api_context.ids["product_card_a"]),
        str(second_missing_id),
    ]

    response = api_context.client.post("/api/visit-plans", json=payload)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PRODUCT_NOT_FOUND"
    assert [detail["value"] for detail in response.json()["error"]["details"]] == [
        str(first_missing_id),
        str(second_missing_id),
    ]
    assert api_context.connection_session.scalar(select(func.count()).select_from(VisitPlan)) == 0


@pytest.mark.parametrize(
    ("constraint_name", "expected_status", "expected_code"),
    [
        (
            "fk_visit_plans_mr_id_medical_representatives",
            404,
            "MR_NOT_FOUND",
        ),
        (
            "fk_visit_plans_hcp_practice_id_hcp_practices",
            422,
            "HCP_PRACTICE_MISMATCH",
        ),
        (
            "fk_visit_plan_products_product_id_products",
            404,
            "PRODUCT_NOT_FOUND",
        ),
        ("pk_visit_plan_products", 422, "DUPLICATE_PRODUCT_ID"),
    ],
)
def test_create_visit_plan_maps_known_constraint_races_to_stable_business_errors(
    api_context: ApiTestContext,
    monkeypatch: pytest.MonkeyPatch,
    constraint_name: str,
    expected_status: int,
    expected_code: str,
) -> None:
    def fail_with_constraint_race(self: VisitPlanRepository, **_: Any) -> None:
        raise _integrity_error(constraint_name)

    monkeypatch.setattr(VisitPlanRepository, "create_plan", fail_with_constraint_race)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/api/visit-plans", json=_valid_payload(api_context))

    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code
    assert api_context.connection_session.scalar(select(func.count()).select_from(VisitPlan)) == 0


def test_create_visit_plan_rejects_hcp_practice_mismatch(api_context: ApiTestContext) -> None:
    payload = _valid_payload(api_context)
    payload["hospitalId"] = str(api_context.ids["hospital_zhongshan"])

    response = api_context.client.post("/api/visit-plans", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "HCP_PRACTICE_MISMATCH"
    assert api_context.connection_session.scalar(select(func.count()).select_from(VisitPlan)) == 0


def test_create_visit_plan_rejects_inactive_hcp_practice(api_context: ApiTestContext) -> None:
    api_context.connection_session.execute(
        update(HcpPractice)
        .where(HcpPractice.hcp_id == api_context.ids["hcp_ruijin_card"])
        .values(is_active=False)
    )
    api_context.connection_session.flush()

    response = api_context.client.post("/api/visit-plans", json=_valid_payload(api_context))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "HCP_PRACTICE_MISMATCH"
    assert api_context.connection_session.scalar(select(func.count()).select_from(VisitPlan)) == 0


@pytest.mark.parametrize(
    ("model", "id_key", "field"),
    [
        (MedicalRepresentative, "mr", "mrId"),
        (Hcp, "hcp_ruijin_card", "hcpId"),
        (Hospital, "hospital_ruijin", "hospitalId"),
        (Department, "department_card", "departmentId"),
        (Product, "product_card_a", "productIds"),
    ],
)
def test_create_visit_plan_rejects_inactive_reference(
    api_context: ApiTestContext,
    model: Any,
    id_key: str,
    field: str,
) -> None:
    api_context.connection_session.execute(
        update(model).where(model.id == api_context.ids[id_key]).values(is_active=False)
    )
    api_context.connection_session.flush()

    response = api_context.client.post("/api/visit-plans", json=_valid_payload(api_context))

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "REFERENCE_INACTIVE"
    assert body["error"]["details"][0]["field"] == field
    assert api_context.connection_session.scalar(select(func.count()).select_from(VisitPlan)) == 0


def test_duplicate_products_are_rejected_before_database_write(
    api_context: ApiTestContext,
) -> None:
    payload = _valid_payload(api_context)
    product_id = str(api_context.ids["product_card_a"])
    payload["productIds"] = [product_id, product_id]

    response = api_context.client.post("/api/visit-plans", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "DUPLICATE_PRODUCT_ID"
    assert api_context.connection_session.scalar(select(func.count()).select_from(VisitPlan)) == 0
    assert (
        api_context.connection_session.scalar(select(func.count()).select_from(VisitPlanProduct))
        == 0
    )


def test_empty_products_are_rejected(api_context: ApiTestContext) -> None:
    payload = _valid_payload(api_context)
    payload["productIds"] = []

    response = api_context.client.post("/api/visit-plans", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PRODUCTS_REQUIRED"
    assert api_context.connection_session.scalar(select(func.count()).select_from(VisitPlan)) == 0


def test_planned_at_must_include_timezone(api_context: ApiTestContext) -> None:
    payload = _valid_payload(api_context)
    payload["plannedAt"] = "2026-09-21T09:30:00"

    response = api_context.client.post("/api/visit-plans", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "TIMEZONE_REQUIRED"
    assert api_context.connection_session.scalar(select(func.count()).select_from(VisitPlan)) == 0


def test_server_owned_fields_are_rejected(api_context: ApiTestContext) -> None:
    payload = _valid_payload(api_context)
    payload["status"] = "PLANNED"

    response = api_context.client.post("/api/visit-plans", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNEXPECTED_FIELD"
    assert api_context.connection_session.scalar(select(func.count()).select_from(VisitPlan)) == 0


def test_framework_404_uses_unified_error_format(api_context: ApiTestContext) -> None:
    response = api_context.client.get("/api/not-a-real-route")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "NOT_FOUND",
            "message": "Not Found",
            "details": [],
        }
    }


def _create_plan_at(context: ApiTestContext, planned_at: datetime) -> UUID:
    payload = _valid_payload(context)
    payload["plannedAt"] = planned_at.isoformat()
    response = context.client.post("/api/visit-plans", json=payload)
    assert response.status_code == 201
    return UUID(response.json()["id"])


def _four_workflow_states(context: ApiTestContext) -> dict[str, UUID]:
    start = datetime(2026, 9, 21, 1, 0, tzinfo=UTC)
    status_names = ["PLANNED", "CHECKED_IN", "CHECKED_OUT", "REPORTED"]
    ids = {
        status_name: _create_plan_at(context, start + timedelta(hours=index))
        for index, status_name in enumerate(status_names)
    }
    session = context.connection_session
    for status_name in status_names[1:]:
        checked_in_at = start + timedelta(hours=status_names.index(status_name), minutes=5)
        visit = Visit(
            plan_id=ids[status_name],
            hospital_latitude_snapshot=Decimal("31.210461"),
            hospital_longitude_snapshot=Decimal("121.473651"),
            check_in_at=checked_in_at,
            check_in_latitude=Decimal("31.210461"),
            check_in_longitude=Decimal("121.473651"),
            check_in_distance_meters=Decimal("0"),
        )
        if status_name in {"CHECKED_OUT", "REPORTED"}:
            visit.check_out_at = checked_in_at + timedelta(minutes=10)
            visit.check_out_latitude = Decimal("31.210461")
            visit.check_out_longitude = Decimal("121.473651")
            visit.check_out_distance_meters = Decimal("0")
        session.add(visit)
        session.flush()
        if status_name == "CHECKED_IN":
            session.add(
                ComplianceFinding(
                    visit_id=visit.id,
                    code=ComplianceFindingCode.CHECKIN_TOO_FAR,
                    phase=CompliancePhase.CHECK_IN,
                    measured_value=Decimal("501"),
                    threshold_value=Decimal("500"),
                    unit=ComplianceUnit.METERS,
                    detected_at=checked_in_at,
                )
            )
        if status_name == "REPORTED":
            session.add(
                VisitReport(
                    visit_id=visit.id,
                    conversation_summary="Discussed clinical evidence.",
                    hcp_feedback="Positive feedback.",
                    submitted_at=checked_in_at + timedelta(minutes=12),
                )
            )
    session.flush()
    return ids


def test_visit_plan_list_paginates_without_product_duplicates(
    api_context: ApiTestContext,
) -> None:
    ids = _four_workflow_states(api_context)

    first_page = api_context.client.get(
        "/api/visit-plans", params={"page": 1, "pageSize": 2, "order": "desc"}
    )
    second_page = api_context.client.get(
        "/api/visit-plans", params={"page": 2, "pageSize": 2, "order": "desc"}
    )

    assert first_page.status_code == second_page.status_code == 200
    assert first_page.json()["total"] == second_page.json()["total"] == 4
    returned_ids = [item["id"] for item in first_page.json()["items"]]
    returned_ids += [item["id"] for item in second_page.json()["items"]]
    assert returned_ids == [str(ids[name]) for name in reversed(list(ids))]
    assert len(set(returned_ids)) == 4
    assert all(len(item["targetProducts"]) == 2 for item in first_page.json()["items"])

    filtered = api_context.client.get("/api/visit-plans", params={"status": "CHECKED_OUT"})
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["id"] == str(ids["CHECKED_OUT"])


@pytest.mark.parametrize("status_name", ["PLANNED", "CHECKED_IN", "CHECKED_OUT", "REPORTED"])
def test_visit_list_filters_each_derived_status(
    api_context: ApiTestContext, status_name: str
) -> None:
    ids = _four_workflow_states(api_context)

    response = api_context.client.get("/api/visits", params={"status": status_name})

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == str(ids[status_name])
    assert response.json()["items"][0]["status"] == status_name


@pytest.mark.parametrize(
    ("parameter", "id_key"),
    [
        ("mrId", "mr"),
        ("hcpId", "hcp_ruijin_card"),
        ("hospitalId", "hospital_ruijin"),
        ("departmentId", "department_card"),
        ("productId", "product_card_a"),
    ],
)
def test_visit_list_filters_reference_ids(
    api_context: ApiTestContext, parameter: str, id_key: str
) -> None:
    _four_workflow_states(api_context)

    matching = api_context.client.get(
        "/api/visits", params={parameter: str(api_context.ids[id_key])}
    )
    missing = api_context.client.get("/api/visits", params={parameter: str(uuid4())})

    assert matching.status_code == missing.status_code == 200
    assert matching.json()["total"] == 4
    assert missing.json()["total"] == 0


def test_visit_list_uses_half_open_planned_date_range(api_context: ApiTestContext) -> None:
    ids = _four_workflow_states(api_context)

    response = api_context.client.get(
        "/api/visits",
        params={
            "plannedFrom": "2026-09-21T02:00:00Z",
            "plannedTo": "2026-09-21T04:00:00Z",
            "order": "asc",
        },
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [
        str(ids["CHECKED_IN"]),
        str(ids["CHECKED_OUT"]),
    ]


def test_visit_list_abnormal_filter_excludes_planned(api_context: ApiTestContext) -> None:
    ids = _four_workflow_states(api_context)

    abnormal = api_context.client.get("/api/visits", params={"isAbnormal": "true"})
    normal_so_far = api_context.client.get("/api/visits", params={"isAbnormal": "false"})

    assert [item["id"] for item in abnormal.json()["items"]] == [str(ids["CHECKED_IN"])]
    assert {item["id"] for item in normal_so_far.json()["items"]} == {
        str(ids["CHECKED_OUT"]),
        str(ids["REPORTED"]),
    }


def test_visit_detail_returns_display_data_and_state_actions(
    api_context: ApiTestContext,
) -> None:
    ids = _four_workflow_states(api_context)
    expected_actions = {
        "PLANNED": ["CHECK_IN"],
        "CHECKED_IN": ["CHECK_OUT"],
        "CHECKED_OUT": ["SUBMIT_REPORT"],
        "REPORTED": ["UPDATE_REPORT"],
    }

    for status_name, workflow_id in ids.items():
        response = api_context.client.get(f"/api/visits/{workflow_id}")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == status_name
        assert body["allowedActions"] == expected_actions[status_name]
        assert body["plan"]["mr"]["name"] == "王晨"
        assert body["plan"]["hcpPractice"]["hospital"]["code"] == "HOSP-SH-RJ"
        expected_coordinates = (
            {"latitude": "31.210460", "longitude": "121.473650"}
            if status_name == "PLANNED"
            else {"latitude": "31.210461", "longitude": "121.473651"}
        )
        assert body["hospitalCoordinates"] == expected_coordinates
        assert len(body["plan"]["targetProducts"]) == 2
        assert (body["actualVisit"] is None) == (status_name == "PLANNED")
        assert (body["report"] is not None) == (status_name == "REPORTED")


def test_visit_detail_missing_workflow_uses_stable_error(api_context: ApiTestContext) -> None:
    missing_id = uuid4()

    response = api_context.client.get(f"/api/visits/{missing_id}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "VISIT_WORKFLOW_NOT_FOUND"
    assert response.json()["error"]["details"] == [
        {"field": "id", "reason": "NOT_FOUND", "value": str(missing_id)}
    ]


def test_check_in_creates_trusted_actual_visit_and_copies_products(
    api_context: ApiTestContext,
) -> None:
    workflow_id = _create_plan_at(api_context, datetime(2026, 9, 22, 1, tzinfo=UTC))
    before = datetime.now(UTC)

    response = api_context.client.post(
        f"/api/visits/{workflow_id}/check-in",
        json={"latitude": 31.210460, "longitude": 121.473650},
    )
    after = datetime.now(UTC)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "CHECKED_IN"
    assert body["allowedActions"] == ["CHECK_OUT"]
    assert body["actualVisit"]["checkIn"]["distanceMeters"] == "0.000000"
    assert len(body["actualVisit"]["products"]) == 2
    assert body["actualVisit"]["complianceFindings"] == []
    assert body["actualVisit"]["complianceStatus"] == "IN_PROGRESS"

    session = api_context.connection_session
    session.expire_all()
    visit = session.scalar(select(Visit).where(Visit.plan_id == workflow_id))
    assert visit is not None
    assert before <= visit.check_in_at <= after
    assert visit.hospital_latitude_snapshot == Decimal("31.210460")
    assert visit.hospital_longitude_snapshot == Decimal("121.473650")
    assert visit.check_in_distance_meters == Decimal("0.000000")
    assert len(visit.products) == 2
    assert session.scalar(select(func.count()).select_from(ComplianceFinding)) == 0


def test_check_in_missing_workflow_returns_visit_not_found(api_context: ApiTestContext) -> None:
    missing_id = uuid4()

    response = api_context.client.post(
        f"/api/visits/{missing_id}/check-in",
        json={"latitude": 31, "longitude": 121},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "VISIT_NOT_FOUND"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("latitude", "NaN"),
        ("latitude", 90.000001),
        ("latitude", -90.000001),
        ("longitude", 180.000001),
        ("longitude", -180.000001),
    ],
)
def test_check_in_rejects_invalid_coordinates(
    api_context: ApiTestContext, field: str, value: object
) -> None:
    workflow_id = _create_plan_at(api_context, datetime(2026, 9, 22, 1, tzinfo=UTC))
    payload: dict[str, object] = {"latitude": 31, "longitude": 121}
    payload[field] = value

    response = api_context.client.post(f"/api/visits/{workflow_id}/check-in", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_COORDINATES"
    assert api_context.connection_session.scalar(select(func.count()).select_from(Visit)) == 0


def test_check_in_accepts_exact_coordinate_boundaries(api_context: ApiTestContext) -> None:
    workflow_id = _create_plan_at(api_context, datetime(2026, 9, 22, 1, tzinfo=UTC))

    response = api_context.client.post(
        f"/api/visits/{workflow_id}/check-in",
        json={"latitude": 90, "longitude": -180},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "CHECKED_IN"


def test_far_check_in_immediately_persists_location_finding(
    api_context: ApiTestContext,
) -> None:
    checked_in_at = datetime(2026, 9, 22, 2, tzinfo=UTC)
    workflow_id = _create_plan_at(api_context, checked_in_at)
    far_latitude = _north_of(Decimal("31.210460"), 600)
    app.dependency_overrides[get_clock] = lambda: FixedClock(checked_in_at)

    response = api_context.client.post(
        f"/api/visits/{workflow_id}/check-in",
        json={"latitude": str(far_latitude), "longitude": "121.473650"},
    )

    assert response.status_code == 200
    actual = response.json()["actualVisit"]
    assert actual["complianceStatus"] == "ABNORMAL"
    assert [finding["code"] for finding in actual["complianceFindings"]] == ["CHECKIN_TOO_FAR"]
    assert actual["complianceFindings"][0]["detectedAt"] == "2026-09-22T02:00:00Z"

    api_context.connection_session.expire_all()
    visit = api_context.connection_session.scalar(select(Visit).where(Visit.plan_id == workflow_id))
    assert visit is not None
    assert [finding.code for finding in visit.compliance_findings] == [
        ComplianceFindingCode.CHECKIN_TOO_FAR
    ]


def test_check_in_rejects_server_owned_fields(api_context: ApiTestContext) -> None:
    workflow_id = _create_plan_at(api_context, datetime(2026, 9, 22, 1, tzinfo=UTC))

    response = api_context.client.post(
        f"/api/visits/{workflow_id}/check-in",
        json={"latitude": 31, "longitude": 121, "checkInAt": "2020-01-01T00:00:00Z"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNEXPECTED_FIELD"
    assert api_context.connection_session.scalar(select(func.count()).select_from(Visit)) == 0


def test_repeated_check_in_does_not_overwrite_original_facts(
    api_context: ApiTestContext,
) -> None:
    workflow_id = _create_plan_at(api_context, datetime(2026, 9, 22, 1, tzinfo=UTC))
    first = api_context.client.post(
        f"/api/visits/{workflow_id}/check-in",
        json={"latitude": 31.210460, "longitude": 121.473650},
    )
    original = first.json()["actualVisit"]["checkIn"]

    repeated = api_context.client.post(
        f"/api/visits/{workflow_id}/check-in",
        json={"latitude": 32, "longitude": 122},
    )

    assert repeated.status_code == 409
    assert repeated.json()["error"]["code"] == "VISIT_ALREADY_CHECKED_IN"
    current = api_context.client.get(f"/api/visits/{workflow_id}").json()
    assert current["actualVisit"]["checkIn"] == original
    assert api_context.connection_session.scalar(select(func.count()).select_from(Visit)) == 1


def test_checked_out_visit_cannot_check_in_again(api_context: ApiTestContext) -> None:
    workflow_id = _create_plan_at(api_context, datetime(2026, 9, 22, 1, tzinfo=UTC))
    first = api_context.client.post(
        f"/api/visits/{workflow_id}/check-in",
        json={"latitude": 31.210460, "longitude": 121.473650},
    )
    original = first.json()["actualVisit"]["checkIn"]
    session = api_context.connection_session
    visit = session.scalar(select(Visit).where(Visit.plan_id == workflow_id))
    assert visit is not None
    visit.check_out_at = visit.check_in_at + timedelta(minutes=10)
    visit.check_out_latitude = visit.check_in_latitude
    visit.check_out_longitude = visit.check_in_longitude
    visit.check_out_distance_meters = visit.check_in_distance_meters
    session.flush()

    response = api_context.client.post(
        f"/api/visits/{workflow_id}/check-in",
        json={"latitude": 32, "longitude": 122},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_VISIT_STATE"
    current = api_context.client.get(f"/api/visits/{workflow_id}").json()
    assert current["actualVisit"]["checkIn"] == original
    assert api_context.connection_session.scalar(select(func.count()).select_from(Visit)) == 1


def test_concurrent_check_in_allows_exactly_one_success(migrated_engine: Engine) -> None:
    with Session(migrated_engine, expire_on_commit=False) as setup_session:
        with setup_session.begin():
            seed_reference_data(setup_session)
        ids = {
            "mr": _id_by_code(setup_session, MedicalRepresentative, "MR-SH-001"),
            "hcp": _id_by_code(setup_session, Hcp, "HCP-SH-001"),
            "hospital": _id_by_code(setup_session, Hospital, "HOSP-SH-RJ"),
            "department": _id_by_code(setup_session, Department, "DEPT-CARD"),
            "product": _id_by_code(setup_session, Product, "PROD-CARD-001"),
        }

    with Session(migrated_engine, expire_on_commit=False) as create_session:
        workflow_id = (
            VisitPlanService(create_session)
            .create(
                CreateVisitPlanCommand(
                    mr_id=ids["mr"],
                    hcp_id=ids["hcp"],
                    hospital_id=ids["hospital"],
                    department_id=ids["department"],
                    planned_at=datetime(2026, 9, 23, 1, tzinfo=UTC),
                    product_ids=[ids["product"]],
                )
            )
            .id
        )

    def independent_session() -> Iterator[Session]:
        with Session(migrated_engine, expire_on_commit=False) as request_session:
            yield request_session

    barrier = Barrier(2)

    def invoke_check_in() -> tuple[int, str]:
        barrier.wait()
        with TestClient(app) as client:
            response = client.post(
                f"/api/visits/{workflow_id}/check-in",
                json={"latitude": 31.210460, "longitude": 121.473650},
            )
            return response.status_code, response.json().get("error", {}).get("code", "")

    app.dependency_overrides[get_db_session] = independent_session
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _: invoke_check_in(), range(2)))

        assert sorted(outcomes) == [
            (200, ""),
            (409, "VISIT_ALREADY_CHECKED_IN"),
        ]
        with Session(migrated_engine) as assertion_session:
            assert (
                assertion_session.scalar(
                    select(func.count()).select_from(Visit).where(Visit.plan_id == workflow_id)
                )
                == 1
            )
    finally:
        app.dependency_overrides.clear()
        with Session(migrated_engine) as cleanup_session, cleanup_session.begin():
            visit_ids = select(Visit.id).where(Visit.plan_id == workflow_id)
            cleanup_session.execute(
                delete(VisitProduct).where(VisitProduct.visit_id.in_(visit_ids))
            )
            cleanup_session.execute(delete(Visit).where(Visit.plan_id == workflow_id))
            cleanup_session.execute(
                delete(VisitPlanProduct).where(VisitPlanProduct.plan_id == workflow_id)
            )
            cleanup_session.execute(delete(VisitPlan).where(VisitPlan.id == workflow_id))


def _north_of(latitude: Decimal, meters: float) -> Decimal:
    return latitude + Decimal(str(degrees(meters / 6_371_008.8)))


def _check_in_at(
    context: ApiTestContext,
    workflow_id: UUID,
    at: datetime,
    *,
    latitude: Decimal = Decimal("31.210460"),
    longitude: Decimal = Decimal("121.473650"),
) -> None:
    app.dependency_overrides[get_clock] = lambda: FixedClock(at)
    response = context.client.post(
        f"/api/visits/{workflow_id}/check-in",
        json={"latitude": str(latitude), "longitude": str(longitude)},
    )
    assert response.status_code == 200


def _check_out_at(
    context: ApiTestContext,
    workflow_id: UUID,
    at: datetime,
    *,
    latitude: Decimal = Decimal("31.210460"),
    longitude: Decimal = Decimal("121.473650"),
) -> Any:
    app.dependency_overrides[get_clock] = lambda: FixedClock(at)
    return context.client.post(
        f"/api/visits/{workflow_id}/check-out",
        json={"latitude": str(latitude), "longitude": str(longitude)},
    )


def test_check_out_after_five_minutes_is_normal(api_context: ApiTestContext) -> None:
    checked_in_at = datetime(2026, 9, 24, 1, tzinfo=UTC)
    workflow_id = _create_plan_at(api_context, checked_in_at)
    _check_in_at(api_context, workflow_id, checked_in_at)

    response = _check_out_at(api_context, workflow_id, checked_in_at + timedelta(minutes=5))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "CHECKED_OUT"
    assert body["allowedActions"] == ["SUBMIT_REPORT"]
    assert body["actualVisit"]["durationSeconds"] == "300.000000"
    assert body["actualVisit"]["checkOut"]["distanceMeters"] == "0.000000"
    assert body["actualVisit"]["complianceStatus"] == "NORMAL"
    assert body["actualVisit"]["complianceFindings"] == []

    api_context.connection_session.expire_all()
    visit = api_context.connection_session.scalar(select(Visit).where(Visit.plan_id == workflow_id))
    assert visit is not None
    assert visit.check_out_at == checked_in_at + timedelta(minutes=5)
    assert visit.duration_seconds == Decimal("300.000000")
    assert visit.check_in_distance_meters == Decimal("0.000000")
    assert visit.check_out_distance_meters == Decimal("0.000000")


def test_check_out_before_five_minutes_saves_duration_finding(
    api_context: ApiTestContext,
) -> None:
    checked_in_at = datetime(2026, 9, 24, 2, tzinfo=UTC)
    workflow_id = _create_plan_at(api_context, checked_in_at)
    _check_in_at(api_context, workflow_id, checked_in_at)

    response = _check_out_at(api_context, workflow_id, checked_in_at + timedelta(seconds=299))

    assert response.status_code == 200
    actual = response.json()["actualVisit"]
    assert actual["complianceStatus"] == "ABNORMAL"
    assert [finding["code"] for finding in actual["complianceFindings"]] == ["DURATION_TOO_SHORT"]
    finding = actual["complianceFindings"][0]
    assert finding["message"]
    assert finding["actualValue"] == "299.000000"
    assert finding["threshold"] == "300.000000"


def test_check_out_saves_checkin_distance_finding(api_context: ApiTestContext) -> None:
    checked_in_at = datetime(2026, 9, 24, 3, tzinfo=UTC)
    workflow_id = _create_plan_at(api_context, checked_in_at)
    far_latitude = _north_of(Decimal("31.210460"), 600)
    _check_in_at(api_context, workflow_id, checked_in_at, latitude=far_latitude)

    response = _check_out_at(api_context, workflow_id, checked_in_at + timedelta(minutes=5))

    assert response.status_code == 200
    actual = response.json()["actualVisit"]
    assert actual["complianceStatus"] == "ABNORMAL"
    assert [finding["code"] for finding in actual["complianceFindings"]] == ["CHECKIN_TOO_FAR"]
    assert Decimal(actual["checkIn"]["distanceMeters"]) > 500


def test_check_out_saves_checkout_distance_finding(api_context: ApiTestContext) -> None:
    checked_in_at = datetime(2026, 9, 24, 4, tzinfo=UTC)
    workflow_id = _create_plan_at(api_context, checked_in_at)
    far_latitude = _north_of(Decimal("31.210460"), 600)
    _check_in_at(api_context, workflow_id, checked_in_at)

    response = _check_out_at(
        api_context,
        workflow_id,
        checked_in_at + timedelta(minutes=5),
        latitude=far_latitude,
    )

    assert response.status_code == 200
    actual = response.json()["actualVisit"]
    assert actual["complianceStatus"] == "ABNORMAL"
    assert [finding["code"] for finding in actual["complianceFindings"]] == ["CHECKOUT_TOO_FAR"]
    assert Decimal(actual["checkOut"]["distanceMeters"]) > 500


def test_check_out_saves_all_findings_in_stable_order(api_context: ApiTestContext) -> None:
    checked_in_at = datetime(2026, 9, 24, 5, tzinfo=UTC)
    workflow_id = _create_plan_at(api_context, checked_in_at)
    check_in_latitude = _north_of(Decimal("31.210460"), 600)
    check_out_latitude = _north_of(Decimal("31.210460"), 700)
    _check_in_at(api_context, workflow_id, checked_in_at, latitude=check_in_latitude)

    response = _check_out_at(
        api_context,
        workflow_id,
        checked_in_at + timedelta(seconds=299),
        latitude=check_out_latitude,
    )

    assert response.status_code == 200
    actual = response.json()["actualVisit"]
    assert actual["complianceStatus"] == "ABNORMAL"
    assert [finding["code"] for finding in actual["complianceFindings"]] == [
        "DURATION_TOO_SHORT",
        "CHECKIN_TOO_FAR",
        "CHECKOUT_TOO_FAR",
    ]
    api_context.connection_session.expire_all()
    visit = api_context.connection_session.scalar(select(Visit).where(Visit.plan_id == workflow_id))
    assert visit is not None
    assert len(visit.compliance_findings) == 3


def test_visit_must_be_checked_in_before_check_out(api_context: ApiTestContext) -> None:
    workflow_id = _create_plan_at(api_context, datetime(2026, 9, 24, 6, tzinfo=UTC))

    response = _check_out_at(api_context, workflow_id, datetime(2026, 9, 24, 7, tzinfo=UTC))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "VISIT_NOT_CHECKED_IN"


def test_repeated_check_out_does_not_overwrite_original_result(
    api_context: ApiTestContext,
) -> None:
    checked_in_at = datetime(2026, 9, 24, 7, tzinfo=UTC)
    workflow_id = _create_plan_at(api_context, checked_in_at)
    _check_in_at(api_context, workflow_id, checked_in_at)
    first = _check_out_at(api_context, workflow_id, checked_in_at + timedelta(minutes=5))
    original = first.json()["actualVisit"]

    repeated = _check_out_at(
        api_context,
        workflow_id,
        checked_in_at + timedelta(minutes=10),
        latitude=Decimal("32"),
        longitude=Decimal("122"),
    )

    assert repeated.status_code == 409
    assert repeated.json()["error"]["code"] == "VISIT_ALREADY_CHECKED_OUT"
    current = api_context.client.get(f"/api/visits/{workflow_id}").json()
    assert current["actualVisit"] == original


def test_check_out_missing_workflow_returns_not_found(api_context: ApiTestContext) -> None:
    response = _check_out_at(api_context, uuid4(), datetime(2026, 9, 24, 8, tzinfo=UTC))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "VISIT_WORKFLOW_NOT_FOUND"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("latitude", "NaN"),
        ("latitude", 90.000001),
        ("latitude", -90.000001),
        ("longitude", 180.000001),
        ("longitude", -180.000001),
    ],
)
def test_check_out_rejects_invalid_coordinates(
    api_context: ApiTestContext, field: str, value: object
) -> None:
    checked_in_at = datetime(2026, 9, 24, 9, tzinfo=UTC)
    workflow_id = _create_plan_at(api_context, checked_in_at)
    _check_in_at(api_context, workflow_id, checked_in_at)
    payload: dict[str, object] = {"latitude": 31, "longitude": 121}
    payload[field] = value

    response = api_context.client.post(f"/api/visits/{workflow_id}/check-out", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_COORDINATES"
    api_context.connection_session.expire_all()
    visit = api_context.connection_session.scalar(select(Visit).where(Visit.plan_id == workflow_id))
    assert visit is not None
    assert visit.check_out_at is None


def test_check_out_rejects_server_owned_fields(api_context: ApiTestContext) -> None:
    checked_in_at = datetime(2026, 9, 24, 10, tzinfo=UTC)
    workflow_id = _create_plan_at(api_context, checked_in_at)
    _check_in_at(api_context, workflow_id, checked_in_at)

    response = api_context.client.post(
        f"/api/visits/{workflow_id}/check-out",
        json={
            "latitude": 31,
            "longitude": 121,
            "checkOutAt": "2026-09-24T10:05:00Z",
            "durationSeconds": 300,
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNEXPECTED_FIELD"


def test_compliance_failure_rolls_back_check_out_and_findings(
    api_context: ApiTestContext,
) -> None:
    checked_in_at = datetime(2026, 9, 24, 11, tzinfo=UTC)
    workflow_id = _create_plan_at(api_context, checked_in_at)
    _check_in_at(api_context, workflow_id, checked_in_at)

    def fail_compliance(_: VisitComplianceInput) -> ComplianceResult:
        raise RuntimeError("simulated compliance failure")

    app.dependency_overrides[get_clock] = lambda: FixedClock(checked_in_at + timedelta(minutes=5))
    app.dependency_overrides[get_compliance_evaluator] = lambda: fail_compliance

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            f"/api/visits/{workflow_id}/check-out",
            json={"latitude": 31.210460, "longitude": 121.473650},
        )

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected server error occurred.",
            "details": [],
        }
    }

    api_context.connection_session.expire_all()
    visit = api_context.connection_session.scalar(select(Visit).where(Visit.plan_id == workflow_id))
    assert visit is not None
    assert visit.check_out_at is None
    assert visit.check_out_latitude is None
    assert visit.check_out_longitude is None
    assert visit.check_out_distance_meters is None
    assert visit.duration_seconds is None
    assert (
        api_context.connection_session.scalar(
            select(func.count())
            .select_from(ComplianceFinding)
            .where(ComplianceFinding.visit_id == visit.id)
        )
        == 0
    )


def _checked_out_workflow(
    context: ApiTestContext,
    checked_in_at: datetime,
    *,
    duration: timedelta = timedelta(minutes=5),
    check_in_latitude: Decimal = Decimal("31.210460"),
    check_out_latitude: Decimal = Decimal("31.210460"),
) -> UUID:
    workflow_id = _create_plan_at(context, checked_in_at)
    _check_in_at(
        context,
        workflow_id,
        checked_in_at,
        latitude=check_in_latitude,
    )
    response = _check_out_at(
        context,
        workflow_id,
        checked_in_at + duration,
        latitude=check_out_latitude,
    )
    assert response.status_code == 200
    return workflow_id


def _valid_report_payload(context: ApiTestContext) -> dict[str, Any]:
    return {
        "conversationSummary": "  Discussed the latest clinical evidence.  ",
        "hcpFeedback": "  The doctor requested long-term safety data.  ",
        "notes": "  Follow up next month.  ",
        "detailingRecords": [
            {
                "productId": str(context.ids["product_card_a"]),
                "contentSummary": "  Presented guideline recommendations.  ",
            }
        ],
        "materialDistributions": [
            {
                "productId": str(context.ids["product_card_a"]),
                "materialCode": "  LIT-001  ",
                "materialName": "  Clinical evidence handout  ",
                "quantity": 0,
                "isCompliant": True,
            }
        ],
    }


def _put_report_at(
    context: ApiTestContext,
    workflow_id: UUID,
    at: datetime,
    payload: dict[str, Any],
) -> Any:
    app.dependency_overrides[get_clock] = lambda: FixedClock(at)
    return context.client.put(f"/api/visits/{workflow_id}/report", json=payload)


def test_submit_report_saves_complete_report_and_changes_status(
    api_context: ApiTestContext,
) -> None:
    checked_in_at = datetime(2026, 9, 25, 1, tzinfo=UTC)
    workflow_id = _checked_out_workflow(api_context, checked_in_at)
    submitted_at = checked_in_at + timedelta(minutes=8)

    response = _put_report_at(
        api_context,
        workflow_id,
        submitted_at,
        _valid_report_payload(api_context),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "REPORTED"
    assert body["allowedActions"] == ["UPDATE_REPORT"]
    report = body["report"]
    assert report["conversationSummary"] == "Discussed the latest clinical evidence."
    assert report["hcpFeedback"] == "The doctor requested long-term safety data."
    assert report["notes"] == "Follow up next month."
    assert report["submittedAt"] == "2026-09-25T01:08:00Z"
    assert report["detailingRecords"] == [
        {
            "productId": str(api_context.ids["product_card_a"]),
            "contentSummary": "Presented guideline recommendations.",
        }
    ]
    assert report["materialDistributions"][0]["materialCode"] == "LIT-001"
    assert report["materialDistributions"][0]["materialName"] == "Clinical evidence handout"
    assert report["materialDistributions"][0]["quantity"] == 0

    api_context.connection_session.expire_all()
    visit = api_context.connection_session.scalar(select(Visit).where(Visit.plan_id == workflow_id))
    assert visit is not None
    assert api_context.connection_session.get(VisitReport, visit.id) is not None
    assert (
        api_context.connection_session.scalar(
            select(func.count())
            .select_from(AcademicDetailingRecord)
            .where(AcademicDetailingRecord.visit_id == visit.id)
        )
        == 1
    )


def test_update_report_replaces_all_mutable_report_data(api_context: ApiTestContext) -> None:
    checked_in_at = datetime(2026, 9, 25, 2, tzinfo=UTC)
    workflow_id = _checked_out_workflow(api_context, checked_in_at)
    first = _put_report_at(
        api_context,
        workflow_id,
        checked_in_at + timedelta(minutes=8),
        _valid_report_payload(api_context),
    )
    original_created_at = first.json()["report"]["createdAt"]
    updated_payload = {
        "conversationSummary": "Updated discussion summary.",
        "hcpFeedback": "Updated doctor feedback.",
        "notes": None,
        "detailingRecords": [
            {
                "productId": str(api_context.ids["product_meta_b"]),
                "contentSummary": "Presented updated metabolic study results.",
            }
        ],
        "materialDistributions": [],
    }

    updated = _put_report_at(
        api_context,
        workflow_id,
        checked_in_at + timedelta(minutes=12),
        updated_payload,
    )

    assert updated.status_code == 200
    report = updated.json()["report"]
    assert updated.json()["status"] == "REPORTED"
    assert report["conversationSummary"] == "Updated discussion summary."
    assert report["notes"] is None
    assert report["createdAt"] == original_created_at
    assert report["submittedAt"] == "2026-09-25T02:12:00Z"
    assert [item["productId"] for item in report["detailingRecords"]] == [
        str(api_context.ids["product_meta_b"])
    ]
    assert report["materialDistributions"] == []

    api_context.connection_session.expire_all()
    visit = api_context.connection_session.scalar(select(Visit).where(Visit.plan_id == workflow_id))
    assert visit is not None
    assert (
        api_context.connection_session.scalar(
            select(func.count())
            .select_from(AcademicDetailingRecord)
            .where(AcademicDetailingRecord.visit_id == visit.id)
        )
        == 1
    )
    assert (
        api_context.connection_session.scalar(
            select(func.count())
            .select_from(MaterialDistribution)
            .where(MaterialDistribution.visit_id == visit.id)
        )
        == 0
    )


@pytest.mark.parametrize("checked_in", [False, True])
def test_report_requires_checked_out_visit(api_context: ApiTestContext, checked_in: bool) -> None:
    at = datetime(2026, 9, 25, 3, tzinfo=UTC)
    workflow_id = _create_plan_at(api_context, at)
    if checked_in:
        _check_in_at(api_context, workflow_id, at)

    response = _put_report_at(
        api_context,
        workflow_id,
        at + timedelta(minutes=10),
        _valid_report_payload(api_context),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "VISIT_NOT_CHECKED_OUT"
    assert api_context.connection_session.scalar(select(func.count()).select_from(VisitReport)) == 0


def test_report_rejects_empty_detailing_products(api_context: ApiTestContext) -> None:
    at = datetime(2026, 9, 25, 4, tzinfo=UTC)
    workflow_id = _checked_out_workflow(api_context, at)
    payload = _valid_report_payload(api_context)
    payload["detailingRecords"] = []

    response = _put_report_at(api_context, workflow_id, at + timedelta(minutes=8), payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "DETAILING_RECORDS_REQUIRED"


def test_report_rejects_product_outside_plan(api_context: ApiTestContext) -> None:
    at = datetime(2026, 9, 25, 5, tzinfo=UTC)
    workflow_id = _checked_out_workflow(api_context, at)
    payload = _valid_report_payload(api_context)
    payload["detailingRecords"] = [
        {
            "productId": str(api_context.ids["product_card_c"]),
            "contentSummary": "This product was not planned.",
        }
    ]

    response = _put_report_at(api_context, workflow_id, at + timedelta(minutes=8), payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REPORT_PRODUCT_NOT_IN_PLAN"
    assert api_context.connection_session.scalar(select(func.count()).select_from(VisitReport)) == 0


def test_report_rejects_duplicate_detailing_product(api_context: ApiTestContext) -> None:
    at = datetime(2026, 9, 25, 6, tzinfo=UTC)
    workflow_id = _checked_out_workflow(api_context, at)
    payload = _valid_report_payload(api_context)
    payload["detailingRecords"].append(dict(payload["detailingRecords"][0]))

    response = _put_report_at(api_context, workflow_id, at + timedelta(minutes=8), payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "DUPLICATE_DETAILING_PRODUCT"


def test_report_rejects_negative_material_quantity(api_context: ApiTestContext) -> None:
    at = datetime(2026, 9, 25, 7, tzinfo=UTC)
    workflow_id = _checked_out_workflow(api_context, at)
    payload = _valid_report_payload(api_context)
    payload["materialDistributions"][0]["quantity"] = -1

    response = _put_report_at(api_context, workflow_id, at + timedelta(minutes=8), payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_MATERIAL_QUANTITY"


def test_report_updates_do_not_change_visit_facts_or_compliance_findings(
    api_context: ApiTestContext,
) -> None:
    checked_in_at = datetime(2026, 9, 25, 8, tzinfo=UTC)
    far_latitude = _north_of(Decimal("31.210460"), 600)
    workflow_id = _checked_out_workflow(
        api_context,
        checked_in_at,
        duration=timedelta(seconds=299),
        check_in_latitude=far_latitude,
    )
    session = api_context.connection_session
    session.expire_all()
    visit = session.scalar(select(Visit).where(Visit.plan_id == workflow_id))
    assert visit is not None
    original_facts = (
        visit.check_in_at,
        visit.check_in_latitude,
        visit.check_in_longitude,
        visit.check_out_at,
        visit.check_out_latitude,
        visit.check_out_longitude,
        visit.duration_seconds,
    )
    original_findings = list(
        session.execute(
            select(
                ComplianceFinding.id,
                ComplianceFinding.code,
                ComplianceFinding.measured_value,
                ComplianceFinding.threshold_value,
            )
            .where(ComplianceFinding.visit_id == visit.id)
            .order_by(ComplianceFinding.code)
        ).all()
    )
    assert len(original_findings) == 2

    first_payload = _valid_report_payload(api_context)
    assert (
        _put_report_at(
            api_context,
            workflow_id,
            checked_in_at + timedelta(minutes=8),
            first_payload,
        ).status_code
        == 200
    )
    first_payload["conversationSummary"] = "Corrected summary."
    assert (
        _put_report_at(
            api_context,
            workflow_id,
            checked_in_at + timedelta(minutes=9),
            first_payload,
        ).status_code
        == 200
    )

    session.expire_all()
    current_visit = session.get(Visit, visit.id)
    assert current_visit is not None
    assert (
        current_visit.check_in_at,
        current_visit.check_in_latitude,
        current_visit.check_in_longitude,
        current_visit.check_out_at,
        current_visit.check_out_latitude,
        current_visit.check_out_longitude,
        current_visit.duration_seconds,
    ) == original_facts
    assert (
        list(
            session.execute(
                select(
                    ComplianceFinding.id,
                    ComplianceFinding.code,
                    ComplianceFinding.measured_value,
                    ComplianceFinding.threshold_value,
                )
                .where(ComplianceFinding.visit_id == visit.id)
                .order_by(ComplianceFinding.code)
            ).all()
        )
        == original_findings
    )


def test_report_replacement_failure_rolls_back_original_report(
    api_context: ApiTestContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    checked_in_at = datetime(2026, 9, 25, 9, tzinfo=UTC)
    workflow_id = _checked_out_workflow(api_context, checked_in_at)
    original_payload = _valid_report_payload(api_context)
    initial = _put_report_at(
        api_context,
        workflow_id,
        checked_in_at + timedelta(minutes=8),
        original_payload,
    )
    assert initial.status_code == 200
    original_report = initial.json()["report"]
    original_replace = VisitPlanRepository.replace_report

    def fail_after_write(self: VisitPlanRepository, **kwargs: Any) -> None:
        original_replace(self, **kwargs)
        raise RuntimeError("simulated report persistence failure")

    monkeypatch.setattr(VisitPlanRepository, "replace_report", fail_after_write)
    changed_payload = _valid_report_payload(api_context)
    changed_payload["conversationSummary"] = "This change must be rolled back."

    with pytest.raises(RuntimeError, match="simulated report persistence failure"):
        _put_report_at(
            api_context,
            workflow_id,
            checked_in_at + timedelta(minutes=12),
            changed_payload,
        )

    api_context.connection_session.expire_all()
    current = api_context.client.get(f"/api/visits/{workflow_id}")
    assert current.status_code == 200
    assert current.json()["report"] == original_report


@pytest.mark.parametrize(
    ("constraint_name", "expected_code"),
    [
        ("pk_academic_detailing_records", "DUPLICATE_DETAILING_PRODUCT"),
        (
            "fk_academic_detailing_records_visit_id_visit_products",
            "REPORT_PRODUCT_NOT_IN_VISIT",
        ),
        (
            "fk_material_distributions_visit_id_visit_products",
            "REPORT_PRODUCT_NOT_IN_VISIT",
        ),
        (
            "ck_material_distributions_quantity_nonnegative",
            "INVALID_MATERIAL_QUANTITY",
        ),
    ],
)
def test_report_maps_known_constraint_races_to_stable_business_errors(
    api_context: ApiTestContext,
    monkeypatch: pytest.MonkeyPatch,
    constraint_name: str,
    expected_code: str,
) -> None:
    checked_in_at = datetime(2026, 9, 25, 10, tzinfo=UTC)
    workflow_id = _checked_out_workflow(api_context, checked_in_at)

    def fail_with_constraint_race(self: VisitPlanRepository, **_: Any) -> None:
        raise _integrity_error(constraint_name)

    monkeypatch.setattr(VisitPlanRepository, "replace_report", fail_with_constraint_race)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.put(
            f"/api/visits/{workflow_id}/report",
            json=_valid_report_payload(api_context),
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == expected_code
    api_context.connection_session.expire_all()
    visit = api_context.connection_session.scalar(select(Visit).where(Visit.plan_id == workflow_id))
    assert visit is not None
    assert visit.report is None
