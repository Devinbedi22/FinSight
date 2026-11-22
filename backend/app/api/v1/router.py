"""Version 1 API router."""

from fastapi import APIRouter
from app.api.v1.comparison import router as comparison_router
from app.api.v1.news import router as news_router
from app.api.v1.research import router as research_router

router = APIRouter()
router.include_router(comparison_router, tags=["comparison"])
router.include_router(news_router, tags=["news"])
router.include_router(research_router, tags=["research"])
