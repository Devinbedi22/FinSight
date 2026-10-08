"""FastAPI application entry point."""

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.v1.router import router as v1_router
from app.core.config import get_settings

app = FastAPI(title=get_settings().app_name)
app.include_router(health_router)
app.include_router(v1_router, prefix="/api/v1")
