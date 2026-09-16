from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from app.core.config import get_settings
from app.db.models import (
    AcademicDetailingRecord,
    ComplianceFinding,
    Department,
    Hcp,
    HcpPractice,
    Hospital,
    HospitalDepartment,
    MaterialDistribution,
    MedicalRepresentative,
    Product,
    Visit,
    VisitPlan,
    VisitPlanProduct,
    VisitProduct,
    VisitReport,
)
from app.db.seed import seed_reference_data

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def migrated_engine() -> Iterator[Engine]:
    database_url = os.getenv("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")

    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    get_settings.cache_clear()

    alembic_config = Config("alembic.ini")
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")

    engine = create_engine(database_url)
    try:
        yield engine
    finally:
        engine.dispose()
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url
        get_settings.cache_clear()


@pytest.fixture
def session(migrated_engine: Engine) -> Iterator[Session]:
    connection = migrated_engine.connect()
    transaction = connection.begin()
    database_session = Session(bind=connection, expire_on_commit=False)
    try:
        yield database_session
    finally:
        database_session.close()
        transaction.rollback()
        connection.close()


def create_visit_plan(session: Session) -> tuple[VisitPlan, Product, Hospital, HcpPractice]:
    mr = MedicalRepresentative(code="MR-001", name="Test MR")
    hospital = Hospital(
        code="HOSP-001",
        name="Test Hospital",
        latitude=Decimal("31.230400"),
        longitude=Decimal("121.473700"),
    )
    department = Department(code="DEPT-001", name="Cardiology")
    hospital_department = HospitalDepartment(
        hospital=hospital,
        department=department,
        display_name="Cardiology Clinic",
    )
    hcp = Hcp(code="HCP-001", name="Test Doctor")
    practice = HcpPractice(hcp=hcp, hospital_department=hospital_department)
    product = Product(code="PROD-001", name="Test Product")
    plan = VisitPlan(
        medical_representative=mr,
        hcp_practice=practice,
        planned_at=datetime(2026, 9, 16, 1, 0, tzinfo=UTC),
        mr_code_snapshot=mr.code,
        mr_name_snapshot=mr.name,
        hcp_code_snapshot=hcp.code,
        hcp_name_snapshot=hcp.name,
        hospital_code_snapshot=hospital.code,
        hospital_name_snapshot=hospital.name,
        department_code_snapshot=department.code,
        department_name_snapshot=department.name,
    )
    session.add_all([plan, product])
    session.flush()
    return plan, product, hospital, practice


def build_visit(plan: VisitPlan, **overrides: Any) -> Visit:
    values: dict[str, Any] = {
        "plan_id": plan.id,
        "hospital_latitude_snapshot": Decimal("31.230400"),
        "hospital_longitude_snapshot": Decimal("121.473700"),
        "check_in_at": datetime(2026, 9, 16, 1, 0, tzinfo=UTC),
        "check_in_latitude": Decimal("31.230400"),
        "check_in_longitude": Decimal("121.473700"),
        "check_in_distance_meters": Decimal("0"),
    }
    values.update(overrides)
    return Visit(**values)


def test_migration_is_at_latest_revision(migrated_engine: Engine) -> None:
    alembic_config = Config("alembic.ini")
    expected_head = ScriptDirectory.from_config(alembic_config).get_current_head()

    with migrated_engine.connect() as connection:
        current_revision = MigrationContext.configure(connection).get_current_revision()

    assert current_revision == expected_head


def test_one_plan_cannot_create_two_visits(session: Session) -> None:
    plan, _, _, _ = create_visit_plan(session)
    session.add(build_visit(plan))
    session.flush()

    with pytest.raises(IntegrityError, match="uq_visits_plan_id"):
        with session.begin_nested():
            session.add(build_visit(plan))
            session.flush()


def test_visit_cannot_reference_same_product_twice(session: Session) -> None:
    plan, product, _, _ = create_visit_plan(session)
    visit = build_visit(plan)
    session.add(visit)
    session.flush()
    session.add(
        VisitProduct(
            visit_id=visit.id,
            product_id=product.id,
            product_code_snapshot=product.code,
            product_name_snapshot=product.name,
        )
    )
    session.flush()

    with pytest.raises(IntegrityError, match="pk_visit_products"):
        with session.begin_nested():
            session.add(
                VisitProduct(
                    visit_id=visit.id,
                    product_id=product.id,
                    product_code_snapshot=product.code,
                    product_name_snapshot=product.name,
                )
            )
            session.flush()


@pytest.mark.parametrize(
    ("field", "invalid_value", "constraint_name"),
    [
        ("check_in_latitude", Decimal("90.000001"), "ck_visits_check_in_latitude_range"),
        (
            "check_in_longitude",
            Decimal("-180.000001"),
            "ck_visits_check_in_longitude_range",
        ),
    ],
)
def test_invalid_visit_coordinates_are_rejected(
    session: Session,
    field: str,
    invalid_value: Decimal,
    constraint_name: str,
) -> None:
    plan, _, _, _ = create_visit_plan(session)

    with pytest.raises(IntegrityError, match=constraint_name):
        with session.begin_nested():
            session.add(build_visit(plan, **{field: invalid_value}))
            session.flush()


def test_duration_is_generated_from_server_timestamps(session: Session) -> None:
    plan, _, _, _ = create_visit_plan(session)
    check_in_at = datetime(2026, 9, 16, 1, 0, tzinfo=UTC)
    visit = build_visit(
        plan,
        check_in_at=check_in_at,
        check_out_at=check_in_at + timedelta(minutes=5),
        check_out_latitude=Decimal("31.230400"),
        check_out_longitude=Decimal("121.473700"),
        check_out_distance_meters=Decimal("0"),
    )
    session.add(visit)
    session.flush()
    session.refresh(visit)

    assert visit.duration_seconds == Decimal("300.000000")


def test_optional_material_product_foreign_key_uses_match_simple(session: Session) -> None:
    plan, _, _, _ = create_visit_plan(session)
    check_in_at = datetime(2026, 9, 16, 1, 0, tzinfo=UTC)
    visit = build_visit(
        plan,
        check_in_at=check_in_at,
        check_out_at=check_in_at + timedelta(minutes=5),
        check_out_latitude=Decimal("31.230400"),
        check_out_longitude=Decimal("121.473700"),
        check_out_distance_meters=Decimal("0"),
    )
    session.add(visit)
    session.flush()
    report = VisitReport(
        visit_id=visit.id,
        conversation_summary="Summary",
        hcp_feedback="Feedback",
        submitted_at=check_in_at + timedelta(minutes=6),
    )
    session.add(report)
    session.flush()

    session.add(
        MaterialDistribution(
            visit_id=visit.id,
            product_id=None,
            material_code="GENERAL-001",
            material_name="General material",
            quantity=1,
            is_compliant=True,
        )
    )
    session.flush()

    with pytest.raises(IntegrityError, match="fk_material_distributions_visit_id_visit_products"):
        with session.begin_nested():
            session.add(
                MaterialDistribution(
                    visit_id=visit.id,
                    product_id=uuid4(),
                    material_code="PRODUCT-001",
                    material_name="Product material",
                    quantity=1,
                    is_compliant=True,
                )
            )
            session.flush()


def test_seed_is_idempotent_and_does_not_create_visit_data(session: Session) -> None:
    first_summary = seed_reference_data(session)
    second_summary = seed_reference_data(session)

    assert first_summary == second_summary
    expected_counts = {
        MedicalRepresentative: 1,
        Hospital: 2,
        Department: 2,
        HospitalDepartment: 3,
        Hcp: 3,
        HcpPractice: 3,
        Product: 3,
    }
    for model, expected_count in expected_counts.items():
        assert session.scalar(select(func.count()).select_from(model)) == expected_count

    ruijin = session.scalar(select(Hospital).where(Hospital.code == "HOSP-SH-RJ"))
    assert ruijin is not None
    assert ruijin.latitude == Decimal("31.210460")
    assert ruijin.longitude == Decimal("121.473650")
    assert {item.department.code for item in ruijin.hospital_departments} == {
        "DEPT-CARD",
        "DEPT-ENDO",
    }

    doctor_zhou = session.scalar(select(Hcp).where(Hcp.code == "HCP-SH-003"))
    assert doctor_zhou is not None
    assert {practice.hospital_department.hospital.code for practice in doctor_zhou.practices} == {
        "HOSP-SH-ZS"
    }

    visit_models = (
        VisitPlan,
        VisitPlanProduct,
        Visit,
        VisitProduct,
        VisitReport,
        AcademicDetailingRecord,
        MaterialDistribution,
        ComplianceFinding,
    )
    for model in visit_models:
        assert session.scalar(select(func.count()).select_from(model)) == 0


def test_foreign_keys_and_orm_relationships_are_correct(session: Session) -> None:
    plan, _, hospital, practice = create_visit_plan(session)

    assert plan.hcp_practice is practice
    assert practice.hospital_department.hospital is hospital
    assert practice in practice.hcp.practices
    assert practice in practice.hospital_department.hcp_practices

    with pytest.raises(IntegrityError, match="fk_hospital_departments_hospital_id_hospitals"):
        with session.begin_nested():
            session.add(
                HospitalDepartment(
                    hospital_id=uuid4(),
                    department_id=practice.hospital_department.department_id,
                )
            )
            session.flush()
