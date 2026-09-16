from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session
from app.core.config import Settings, get_settings
from app.db.models import (
    AcademicDetailingRecord,
    ComplianceFinding,
    ComplianceFindingCode,
    CompliancePhase,
    ComplianceUnit,
    HcpPractice,
    MaterialDistribution,
    MedicalRepresentative,
    Product,
    Visit,
    VisitPlan,
    VisitProduct,
    VisitReport,
)
from app.db.seed import seed_reference_data
from app.main import app

pytestmark = pytest.mark.integration


@dataclass(frozen=True)
class DashboardApiContext:
    client: TestClient
    session: Session
    mr_id: UUID
    practice_id: UUID
    products: dict[str, Product]


@pytest.fixture
def dashboard_context(migrated_engine: Engine) -> Iterator[DashboardApiContext]:
    connection = migrated_engine.connect()
    outer_transaction = connection.begin()
    setup_session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    with setup_session.begin():
        seed_reference_data(setup_session)

    mr_id = setup_session.scalar(
        select(MedicalRepresentative.id).where(MedicalRepresentative.code == "MR-SH-001")
    )
    practice_id = setup_session.scalar(select(HcpPractice.id).limit(1))
    products = {
        product.code: product
        for product in setup_session.scalars(select(Product).order_by(Product.code)).all()
    }
    assert isinstance(mr_id, UUID)
    assert isinstance(practice_id, UUID)
    setup_session.close()

    def override_session() -> Iterator[Session]:
        with Session(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        ) as request_session:
            yield request_session

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        business_timezone="Asia/Shanghai",
    )
    data_session = Session(bind=connection, expire_on_commit=False)
    try:
        with TestClient(app) as client:
            yield DashboardApiContext(
                client=client,
                session=data_session,
                mr_id=mr_id,
                practice_id=practice_id,
                products=products,
            )
    finally:
        app.dependency_overrides.clear()
        data_session.close()
        outer_transaction.rollback()
        connection.close()


def _add_visit(
    context: DashboardApiContext,
    *,
    check_in_at: datetime,
    product_codes: Sequence[str],
    check_out: bool = True,
    abnormal: bool = False,
    with_report_rows: bool = False,
) -> Visit:
    plan = VisitPlan(
        mr_id=context.mr_id,
        hcp_practice_id=context.practice_id,
        planned_at=check_in_at,
        mr_code_snapshot="MR-SH-001",
        mr_name_snapshot="王晨",
        hcp_code_snapshot="HCP-SH-001",
        hcp_name_snapshot="陈医生",
        hospital_code_snapshot="HOSP-SH-RJ",
        hospital_name_snapshot="上海交通大学医学院附属瑞金医院",
        department_code_snapshot="DEPT-CARD",
        department_name_snapshot="心内科",
    )
    context.session.add(plan)
    context.session.flush()

    check_out_at = check_in_at + timedelta(minutes=10) if check_out else None
    visit = Visit(
        plan_id=plan.id,
        hospital_latitude_snapshot=Decimal("31.210460"),
        hospital_longitude_snapshot=Decimal("121.473650"),
        check_in_at=check_in_at,
        check_in_latitude=Decimal("31.210460"),
        check_in_longitude=Decimal("121.473650"),
        check_in_distance_meters=Decimal("0"),
        check_out_at=check_out_at,
        check_out_latitude=Decimal("31.210460") if check_out else None,
        check_out_longitude=Decimal("121.473650") if check_out else None,
        check_out_distance_meters=Decimal("0") if check_out else None,
    )
    context.session.add(visit)
    context.session.flush()

    selected_products = [context.products[code] for code in product_codes]
    context.session.add_all(
        [
            VisitProduct(
                visit_id=visit.id,
                product_id=product.id,
                product_code_snapshot=product.code,
                product_name_snapshot=product.name,
            )
            for product in selected_products
        ]
    )
    context.session.flush()

    if abnormal:
        assert check_out_at is not None
        context.session.add(
            ComplianceFinding(
                visit_id=visit.id,
                code=ComplianceFindingCode.DURATION_TOO_SHORT,
                phase=CompliancePhase.CHECK_OUT,
                measured_value=Decimal("299"),
                threshold_value=Decimal("300"),
                unit=ComplianceUnit.SECONDS,
                detected_at=check_out_at,
            )
        )

    if with_report_rows:
        assert check_out_at is not None
        context.session.add(
            VisitReport(
                visit_id=visit.id,
                conversation_summary="Discussed evidence.",
                hcp_feedback="Positive feedback.",
                submitted_at=check_out_at + timedelta(minutes=1),
            )
        )
        context.session.flush()
        context.session.add_all(
            [
                AcademicDetailingRecord(
                    visit_id=visit.id,
                    product_id=product.id,
                    content_summary=f"Detailing for {product.code}",
                )
                for product in selected_products
            ]
        )
        first_product = selected_products[0]
        context.session.add_all(
            [
                MaterialDistribution(
                    visit_id=visit.id,
                    product_id=first_product.id,
                    material_code=f"MAT-{index}",
                    material_name=f"Material {index}",
                    quantity=1,
                    is_compliant=True,
                )
                for index in range(2)
            ]
        )

    context.session.flush()
    return visit


def _get_dashboard(context: DashboardApiContext, month: str) -> dict[str, Any]:
    response = context.client.get(
        "/api/dashboard/monthly-visits-by-product",
        params={"month": month},
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, dict)
    return body


def _items_by_code(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["product"]["code"]: item for item in body["items"]}


def test_single_product_counts_multiple_visits(dashboard_context: DashboardApiContext) -> None:
    for day in range(1, 4):
        _add_visit(
            dashboard_context,
            check_in_at=datetime(2026, 9, day, 1, tzinfo=UTC),
            product_codes=["PROD-CARD-001"],
        )

    body = _get_dashboard(dashboard_context, "2026-09")

    assert body["items"] == [
        {
            "product": {
                "id": str(dashboard_context.products["PROD-CARD-001"].id),
                "code": "PROD-CARD-001",
                "name": "心血管产品 A",
            },
            "totalCount": 3,
            "normalCount": 3,
            "abnormalCount": 0,
            "pendingCount": 0,
        }
    ]


def test_one_visit_counts_once_for_each_product(dashboard_context: DashboardApiContext) -> None:
    _add_visit(
        dashboard_context,
        check_in_at=datetime(2026, 9, 5, 1, tzinfo=UTC),
        product_codes=["PROD-CARD-001", "PROD-META-001", "PROD-CARD-002"],
    )
    _add_visit(
        dashboard_context,
        check_in_at=datetime(2026, 9, 5, 2, tzinfo=UTC),
        product_codes=["PROD-CARD-001"],
    )

    body = _get_dashboard(dashboard_context, "2026-09")
    items = _items_by_code(body)

    assert set(items) == {"PROD-CARD-001", "PROD-META-001", "PROD-CARD-002"}
    assert items["PROD-CARD-001"]["totalCount"] == 2
    assert items["PROD-META-001"]["totalCount"] == 1
    assert items["PROD-CARD-002"]["totalCount"] == 1
    assert body["items"][0]["product"]["code"] == "PROD-CARD-001"
    assert [item["product"]["name"] for item in body["items"][1:]] == sorted(
        ["代谢产品 B", "心血管产品 C"]
    )

    filtered = dashboard_context.client.get(
        "/api/dashboard/monthly-visits-by-product",
        params={
            "month": "2026-09",
            "productId": str(dashboard_context.products["PROD-META-001"].id),
        },
    )
    assert filtered.status_code == 200
    assert [item["product"]["code"] for item in filtered.json()["items"]] == ["PROD-META-001"]


def test_detailing_and_material_rows_do_not_multiply_visit_count(
    dashboard_context: DashboardApiContext,
) -> None:
    _add_visit(
        dashboard_context,
        check_in_at=datetime(2026, 9, 6, 1, tzinfo=UTC),
        product_codes=["PROD-CARD-001", "PROD-META-001"],
        with_report_rows=True,
    )

    items = _items_by_code(_get_dashboard(dashboard_context, "2026-09"))

    assert items["PROD-CARD-001"]["totalCount"] == 1
    assert items["PROD-META-001"]["totalCount"] == 1


def test_normal_and_abnormal_visits_are_classified_once(
    dashboard_context: DashboardApiContext,
) -> None:
    _add_visit(
        dashboard_context,
        check_in_at=datetime(2026, 9, 7, 1, tzinfo=UTC),
        product_codes=["PROD-CARD-001"],
    )
    abnormal_visit = _add_visit(
        dashboard_context,
        check_in_at=datetime(2026, 9, 8, 1, tzinfo=UTC),
        product_codes=["PROD-CARD-001"],
        abnormal=True,
    )
    dashboard_context.session.add(
        ComplianceFinding(
            visit_id=abnormal_visit.id,
            code=ComplianceFindingCode.CHECKIN_TOO_FAR,
            phase=CompliancePhase.CHECK_IN,
            measured_value=Decimal("501"),
            threshold_value=Decimal("500"),
            unit=ComplianceUnit.METERS,
            detected_at=abnormal_visit.check_in_at,
        )
    )
    dashboard_context.session.flush()

    item = _get_dashboard(dashboard_context, "2026-09")["items"][0]

    assert item["totalCount"] == 2
    assert item["normalCount"] == 1
    assert item["abnormalCount"] == 1
    assert item["pendingCount"] == 0


def test_checked_in_visit_is_pending_not_normal(
    dashboard_context: DashboardApiContext,
) -> None:
    _add_visit(
        dashboard_context,
        check_in_at=datetime(2026, 9, 9, 1, tzinfo=UTC),
        product_codes=["PROD-CARD-001"],
        check_out=False,
    )

    item = _get_dashboard(dashboard_context, "2026-09")["items"][0]

    assert item["totalCount"] == 1
    assert item["normalCount"] == 0
    assert item["abnormalCount"] == 0
    assert item["pendingCount"] == 1


def test_business_month_uses_half_open_utc_boundaries(
    dashboard_context: DashboardApiContext,
) -> None:
    start_utc = datetime(2026, 8, 31, 16, tzinfo=UTC)
    end_utc = datetime(2026, 9, 30, 16, tzinfo=UTC)
    for check_in_at in (
        start_utc - timedelta(microseconds=1),
        start_utc,
        end_utc - timedelta(microseconds=1),
        end_utc,
    ):
        _add_visit(
            dashboard_context,
            check_in_at=check_in_at,
            product_codes=["PROD-CARD-001"],
        )

    body = _get_dashboard(dashboard_context, "2026-09")

    assert body["rangeStartUtc"] == "2026-08-31T16:00:00Z"
    assert body["rangeEndUtc"] == "2026-09-30T16:00:00Z"
    assert body["items"][0]["totalCount"] == 2


def test_business_timezone_can_include_previous_utc_date(
    dashboard_context: DashboardApiContext,
) -> None:
    _add_visit(
        dashboard_context,
        check_in_at=datetime(2026, 8, 31, 17, tzinfo=UTC),
        product_codes=["PROD-CARD-001"],
    )

    september = _get_dashboard(dashboard_context, "2026-09")
    august = _get_dashboard(dashboard_context, "2026-08")

    assert september["businessTimezone"] == "Asia/Shanghai"
    assert september["items"][0]["totalCount"] == 1
    assert august["items"] == []


def test_month_without_visits_returns_empty_items(
    dashboard_context: DashboardApiContext,
) -> None:
    body = _get_dashboard(dashboard_context, "2025-01")

    assert body["items"] == []
    assert body["month"] == "2025-01"


@pytest.mark.parametrize("month", [None, "2026-9", "2026-00", "2026-13", "not-a-month"])
def test_invalid_month_uses_stable_business_error(
    dashboard_context: DashboardApiContext, month: str | None
) -> None:
    params = {} if month is None else {"month": month}

    response = dashboard_context.client.get(
        "/api/dashboard/monthly-visits-by-product",
        params=params,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_MONTH"
    assert response.json()["error"]["details"][0]["field"] == "month"
