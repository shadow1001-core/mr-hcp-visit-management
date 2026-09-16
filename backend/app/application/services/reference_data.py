from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.repositories.reference_data import ReferenceDataRepository


@dataclass(frozen=True)
class ReferenceOption:
    id: UUID
    code: str
    name: str


@dataclass(frozen=True)
class PlanningPracticeOption:
    id: UUID
    hcp: ReferenceOption
    hospital: ReferenceOption
    department: ReferenceOption


@dataclass(frozen=True)
class VisitPlanningReferenceData:
    medical_representatives: list[ReferenceOption]
    products: list[ReferenceOption]
    practices: list[PlanningPracticeOption]


class ReferenceDataService:
    def __init__(self, session: Session) -> None:
        self.repository = ReferenceDataRepository(session)

    def visit_planning(self) -> VisitPlanningReferenceData:
        representatives = self.repository.list_active_medical_representatives()
        products = self.repository.list_active_products()
        practices = self.repository.list_active_hcp_practices()
        return VisitPlanningReferenceData(
            medical_representatives=[
                ReferenceOption(id=item.id, code=item.code, name=item.name)
                for item in representatives
            ],
            products=[
                ReferenceOption(id=item.id, code=item.code, name=item.name) for item in products
            ],
            practices=[
                PlanningPracticeOption(
                    id=practice.id,
                    hcp=ReferenceOption(
                        id=practice.hcp.id,
                        code=practice.hcp.code,
                        name=practice.hcp.name,
                    ),
                    hospital=ReferenceOption(
                        id=practice.hospital_department.hospital.id,
                        code=practice.hospital_department.hospital.code,
                        name=practice.hospital_department.hospital.name,
                    ),
                    department=ReferenceOption(
                        id=practice.hospital_department.department.id,
                        code=practice.hospital_department.department.code,
                        name=practice.hospital_department.department.name,
                    ),
                )
                for practice in practices
            ],
        )
