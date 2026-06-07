from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from db import get_db
from models import ExplanationCache
from routers.super_admin import no_store, require_super_admin
from services.llm_explain import explanation_cache_stats


router = APIRouter(
    prefix="/api/admin",
    tags=["explanation-admin"],
    dependencies=[Depends(require_super_admin)],
)


@router.get("/explanations/{explanation_id}")
def replay_explanation(
    explanation_id: int,
    response: Response,
    db: Session = Depends(get_db),
):
    no_store(response)
    row = db.query(ExplanationCache).filter(ExplanationCache.id == explanation_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Explanation not found")
    return {
        "id": row.id,
        "factory_id": row.factory_id,
        "snapshot_hash": row.snapshot_hash,
        "briefing_date": row.briefing_date.isoformat(),
        "language": row.language,
        "explanation": row.explanation_json,
        "model_name": row.model_name,
        "token_usage": row.token_usage,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/explanation-cache/stats")
def cache_stats(
    response: Response,
    db: Session = Depends(get_db),
):
    no_store(response)
    return explanation_cache_stats(db)
