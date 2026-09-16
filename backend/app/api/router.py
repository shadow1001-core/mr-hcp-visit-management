from fastapi import APIRouter

from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.health import router as health_router
from app.api.routes.reference_data import router as reference_data_router
from app.api.routes.visit_plans import router as visit_plans_router
from app.api.routes.visits import router as visits_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(reference_data_router)
api_router.include_router(dashboard_router)
api_router.include_router(visit_plans_router)
api_router.include_router(visits_router)
