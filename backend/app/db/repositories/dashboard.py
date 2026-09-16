from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, exists, func, select
from sqlalchemy.orm import Session

from app.db.models import ComplianceFinding, Product, Visit, VisitProduct


@dataclass(frozen=True)
class MonthlyProductVisitStat:
    product_id: UUID
    product_code: str
    product_name: str
    total_count: int
    normal_count: int
    abnormal_count: int
    pending_count: int


class DashboardRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def monthly_visits_by_product(
        self,
        *,
        start_utc: datetime,
        end_utc: datetime,
        product_id: UUID | None = None,
    ) -> list[MonthlyProductVisitStat]:
        has_finding = exists().where(ComplianceFinding.visit_id == Visit.id)
        eligible_visits = (
            select(
                Visit.id.label("visit_id"),
                Visit.check_out_at.is_(None).label("is_pending"),
                and_(Visit.check_out_at.is_not(None), has_finding).label("is_abnormal"),
            )
            .where(Visit.check_in_at >= start_utc, Visit.check_in_at < end_utc)
            .cte("eligible_visits")
        )
        product_visits_query = (
            select(
                VisitProduct.product_id,
                eligible_visits.c.visit_id,
                eligible_visits.c.is_pending,
                eligible_visits.c.is_abnormal,
            )
            .select_from(eligible_visits)
            .join(VisitProduct, VisitProduct.visit_id == eligible_visits.c.visit_id)
        )
        if product_id is not None:
            product_visits_query = product_visits_query.where(VisitProduct.product_id == product_id)
        product_visits = product_visits_query.cte("product_visits")

        total_count = func.count().label("total_count")
        normal_count = (
            func.count()
            .filter(~product_visits.c.is_pending, ~product_visits.c.is_abnormal)
            .label("normal_count")
        )
        abnormal_count = (
            func.count()
            .filter(~product_visits.c.is_pending, product_visits.c.is_abnormal)
            .label("abnormal_count")
        )
        pending_count = func.count().filter(product_visits.c.is_pending).label("pending_count")
        statement = (
            select(
                Product.id.label("product_id"),
                Product.code.label("product_code"),
                Product.name.label("product_name"),
                total_count,
                normal_count,
                abnormal_count,
                pending_count,
            )
            .join(product_visits, product_visits.c.product_id == Product.id)
            .group_by(Product.id, Product.code, Product.name)
            .order_by(total_count.desc(), Product.name.asc(), Product.id.asc())
        )

        return [
            MonthlyProductVisitStat(
                product_id=row.product_id,
                product_code=row.product_code,
                product_name=row.product_name,
                total_count=row.total_count,
                normal_count=row.normal_count,
                abnormal_count=row.abnormal_count,
                pending_count=row.pending_count,
            )
            for row in self.session.execute(statement)
        ]

    def product_exists(self, product_id: UUID) -> bool:
        return self.session.scalar(select(Product.id).where(Product.id == product_id)) is not None
