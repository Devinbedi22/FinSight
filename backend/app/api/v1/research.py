"""Evidence-grounded research assistant API."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.research_assistant import ResearchQuestionError, answer_research_question
from app.services.research_llm import provider_status

router = APIRouter()


class ResearchHistoryTurn(BaseModel):
    question: Annotated[str, Field(min_length=1, max_length=500)]
    companies: Annotated[list[Annotated[str, StringConstraints(max_length=12)]], Field(max_length=4)] = Field(default_factory=list)
    finding_citations: Annotated[list[Annotated[str, StringConstraints(max_length=100)]], Field(max_length=20)] = Field(default_factory=list)


class ResearchQuestion(BaseModel):
    question: Annotated[str, Field(min_length=1, max_length=500)]
    history: Annotated[list[ResearchHistoryTurn], Field(max_length=6)] = Field(default_factory=list)


@router.post("/research/ask")
def ask_research_question(payload: ResearchQuestion, session: Session = Depends(get_db)) -> dict:
    try:
        return answer_research_question(
            payload.question,
            session,
            [item.model_dump() for item in payload.history],
        )
    except ResearchQuestionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/research/status")
def research_status() -> dict:
    """Return safe provider status; credentials and endpoint secrets are never exposed."""
    return provider_status()
