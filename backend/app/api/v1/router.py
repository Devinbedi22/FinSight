"""Version 1 API router."""

from fastapi import APIRouter
from app.api.v1.news import router as news_router

router = APIRouter()
router.include_router(news_router, tags=["news"])
