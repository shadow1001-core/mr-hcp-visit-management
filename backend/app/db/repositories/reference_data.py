from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.models import (
    Department,
    Hcp,
    HcpPractice,
    Hospital,
    HospitalDepartment,
    MedicalRepresentative,
    Product,
)


class ReferenceDataRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_active_medical_representatives(self) -> list[MedicalRepresentative]:
        return list(
            self.session.scalars(
                select(MedicalRepresentative)
                .where(MedicalRepresentative.is_active.is_(True))
                .order_by(MedicalRepresentative.name, MedicalRepresentative.code)
            ).all()
        )

    def list_active_products(self) -> list[Product]:
        return list(
            self.session.scalars(
                select(Product)
                .where(Product.is_active.is_(True))
                .order_by(Product.name, Product.code)
            ).all()
        )

    def list_active_hcp_practices(self) -> list[HcpPractice]:
        return list(
            self.session.scalars(
                select(HcpPractice)
                .join(Hcp, HcpPractice.hcp_id == Hcp.id)
                .join(
                    HospitalDepartment,
                    HcpPractice.hospital_department_id == HospitalDepartment.id,
                )
                .join(Hospital, HospitalDepartment.hospital_id == Hospital.id)
                .join(Department, HospitalDepartment.department_id == Department.id)
                .where(
                    HcpPractice.is_active.is_(True),
                    Hcp.is_active.is_(True),
                    HospitalDepartment.is_active.is_(True),
                    Hospital.is_active.is_(True),
                    Department.is_active.is_(True),
                )
                .options(
                    joinedload(HcpPractice.hcp),
                    joinedload(HcpPractice.hospital_department).joinedload(
                        HospitalDepartment.hospital
                    ),
                    joinedload(HcpPractice.hospital_department).joinedload(
                        HospitalDepartment.department
                    ),
                )
                .order_by(
                    Hospital.name,
                    Department.name,
                    Hcp.name,
                    Hcp.code,
                )
            ).all()
        )
