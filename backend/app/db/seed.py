from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.db.models import (
    Department,
    Hcp,
    HcpPractice,
    Hospital,
    HospitalDepartment,
    MedicalRepresentative,
    Product,
)


@dataclass(frozen=True)
class SeedSummary:
    medical_representatives: int
    hospitals: int
    departments: int
    hospital_departments: int
    hcps: int
    hcp_practices: int
    products: int


class SeedNotAllowedError(RuntimeError):
    """Raised when demo data seeding is forbidden for the current environment."""


def _seed_medical_representative(session: Session) -> MedicalRepresentative:
    representative = session.scalar(
        select(MedicalRepresentative).where(MedicalRepresentative.code == "MR-SH-001")
    )
    if representative is None:
        representative = MedicalRepresentative(code="MR-SH-001", name="王晨")
        session.add(representative)
    representative.name = "王晨"
    representative.is_active = True
    return representative


def _seed_hospital(
    session: Session,
    *,
    code: str,
    name: str,
    address: str,
    latitude: str,
    longitude: str,
) -> Hospital:
    hospital = session.scalar(select(Hospital).where(Hospital.code == code))
    if hospital is None:
        hospital = Hospital(
            code=code, name=name, latitude=Decimal(latitude), longitude=Decimal(longitude)
        )
        session.add(hospital)
    hospital.name = name
    hospital.address = address
    hospital.latitude = Decimal(latitude)
    hospital.longitude = Decimal(longitude)
    hospital.is_active = True
    return hospital


def _seed_department(session: Session, *, code: str, name: str) -> Department:
    department = session.scalar(select(Department).where(Department.code == code))
    if department is None:
        department = Department(code=code, name=name)
        session.add(department)
    department.name = name
    department.is_active = True
    return department


def _seed_hospital_department(
    session: Session,
    *,
    hospital: Hospital,
    department: Department,
    display_name: str,
) -> HospitalDepartment:
    session.flush()
    hospital_department = session.scalar(
        select(HospitalDepartment).where(
            HospitalDepartment.hospital_id == hospital.id,
            HospitalDepartment.department_id == department.id,
        )
    )
    if hospital_department is None:
        hospital_department = HospitalDepartment(
            hospital=hospital,
            department=department,
            display_name=display_name,
        )
        session.add(hospital_department)
    hospital_department.display_name = display_name
    hospital_department.is_active = True
    return hospital_department


def _seed_hcp(session: Session, *, code: str, name: str, professional_title: str) -> Hcp:
    hcp = session.scalar(select(Hcp).where(Hcp.code == code))
    if hcp is None:
        hcp = Hcp(code=code, name=name)
        session.add(hcp)
    hcp.name = name
    hcp.professional_title = professional_title
    hcp.is_active = True
    return hcp


def _seed_hcp_practice(
    session: Session, *, hcp: Hcp, hospital_department: HospitalDepartment
) -> HcpPractice:
    session.flush()
    practice = session.scalar(
        select(HcpPractice).where(
            HcpPractice.hcp_id == hcp.id,
            HcpPractice.hospital_department_id == hospital_department.id,
        )
    )
    if practice is None:
        practice = HcpPractice(hcp=hcp, hospital_department=hospital_department)
        session.add(practice)
    practice.is_active = True
    return practice


def _seed_product(session: Session, *, code: str, name: str) -> Product:
    product = session.scalar(select(Product).where(Product.code == code))
    if product is None:
        product = Product(code=code, name=name)
        session.add(product)
    product.name = name
    product.is_active = True
    return product


def seed_reference_data(session: Session) -> SeedSummary:
    """Create or refresh deterministic local reference data without committing."""

    _seed_medical_representative(session)

    ruijin = _seed_hospital(
        session,
        code="HOSP-SH-RJ",
        name="上海交通大学医学院附属瑞金医院",
        address="上海市黄浦区瑞金二路197号",
        latitude="31.210460",
        longitude="121.473650",
    )
    zhongshan = _seed_hospital(
        session,
        code="HOSP-SH-ZS",
        name="复旦大学附属中山医院",
        address="上海市徐汇区枫林路180号",
        latitude="31.197750",
        longitude="121.453720",
    )

    cardiology = _seed_department(session, code="DEPT-CARD", name="心内科")
    endocrinology = _seed_department(session, code="DEPT-ENDO", name="内分泌科")

    ruijin_cardiology = _seed_hospital_department(
        session,
        hospital=ruijin,
        department=cardiology,
        display_name="心血管内科",
    )
    ruijin_endocrinology = _seed_hospital_department(
        session,
        hospital=ruijin,
        department=endocrinology,
        display_name="内分泌代谢科",
    )
    zhongshan_cardiology = _seed_hospital_department(
        session,
        hospital=zhongshan,
        department=cardiology,
        display_name="心内科",
    )

    doctor_chen = _seed_hcp(
        session,
        code="HCP-SH-001",
        name="陈医生",
        professional_title="主任医师",
    )
    doctor_li = _seed_hcp(
        session,
        code="HCP-SH-002",
        name="李医生",
        professional_title="副主任医师",
    )
    doctor_zhou = _seed_hcp(
        session,
        code="HCP-SH-003",
        name="周医生",
        professional_title="主治医师",
    )

    _seed_hcp_practice(session, hcp=doctor_chen, hospital_department=ruijin_cardiology)
    _seed_hcp_practice(session, hcp=doctor_li, hospital_department=ruijin_endocrinology)
    _seed_hcp_practice(session, hcp=doctor_zhou, hospital_department=zhongshan_cardiology)

    _seed_product(session, code="PROD-CARD-001", name="心血管产品 A")
    _seed_product(session, code="PROD-META-001", name="代谢产品 B")
    _seed_product(session, code="PROD-CARD-002", name="心血管产品 C")

    session.flush()
    return SeedSummary(
        medical_representatives=1,
        hospitals=2,
        departments=2,
        hospital_departments=3,
        hcps=3,
        hcp_practices=3,
        products=3,
    )


def run_seed(settings: Settings) -> SeedSummary:
    if settings.app_env == "production":
        msg = "Refusing to seed data when APP_ENV=production"
        raise SeedNotAllowedError(msg)

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        with session_factory.begin() as session:
            return seed_reference_data(session)
    finally:
        engine.dispose()


def main() -> None:
    try:
        summary = run_seed(get_settings())
    except SeedNotAllowedError as error:
        raise SystemExit(str(error)) from None
    print(
        "Seed complete: "
        f"{summary.medical_representatives} MR, "
        f"{summary.hospitals} hospitals, "
        f"{summary.hospital_departments} hospital departments, "
        f"{summary.hcps} HCPs, "
        f"{summary.hcp_practices} practices, "
        f"{summary.products} products"
    )


if __name__ == "__main__":
    main()
