from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.application.clock import Clock, SystemClock
from app.application.services.visit_plans import ComplianceEvaluator
from app.db.session import SessionLocal
from app.domain.compliance import evaluate_visit_compliance


def get_db_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def get_clock() -> Clock:
    return SystemClock()


def get_compliance_evaluator() -> ComplianceEvaluator:
    return evaluate_visit_compliance
