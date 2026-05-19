from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ai_agent import build_ai_tool_context, initialize_groq_llm
from auth import check_permissions
from db import get_db
from models import Factory, User


router = APIRouter(tags=["integrations"])


class TelegramIntegrationResponse(BaseModel):
    telegram_bot_token: Optional[str] = None
    is_configured: bool


class TelegramIntegrationRequest(BaseModel):
    telegram_bot_token: Optional[str] = Field(default=None, max_length=255)


class N8NAIWebhookRequest(BaseModel):
    factory_id: int | str
    user_message: str = Field(..., min_length=1)


class N8NAIWebhookResponse(BaseModel):
    response: str


def _factory_for_user(db: Session, current_user: User) -> Factory:
    factory = db.query(Factory).filter(Factory.id == current_user.factory_id).first()
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Factory not found for current user",
        )
    return factory


def _normalize_token(token: Optional[str]) -> Optional[str]:
    cleaned = (token or "").strip()
    return cleaned or None


@router.get("/api/integrations/telegram", response_model=TelegramIntegrationResponse)
def get_telegram_integration(
    current_user: User = Depends(check_permissions(["Owner", "Sub-Owner"])),
    db: Session = Depends(get_db),
):
    factory = _factory_for_user(db, current_user)
    return TelegramIntegrationResponse(
        telegram_bot_token=factory.telegram_bot_token,
        is_configured=bool(factory.telegram_bot_token),
    )


@router.post("/api/integrations/telegram", response_model=TelegramIntegrationResponse)
def save_telegram_integration(
    payload: TelegramIntegrationRequest,
    current_user: User = Depends(check_permissions(["Owner", "Sub-Owner"])),
    db: Session = Depends(get_db),
):
    factory = _factory_for_user(db, current_user)
    factory.telegram_bot_token = _normalize_token(payload.telegram_bot_token)
    db.commit()
    db.refresh(factory)
    return TelegramIntegrationResponse(
        telegram_bot_token=factory.telegram_bot_token,
        is_configured=bool(factory.telegram_bot_token),
    )


@router.post("/api/ai/n8n-webhook", response_model=N8NAIWebhookResponse)
def telegram_ai_n8n_webhook(payload: N8NAIWebhookRequest, db: Session = Depends(get_db)):
    try:
        factory_id = int(payload.factory_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="factory_id must be a valid integer",
        ) from exc

    factory = db.query(Factory).filter(Factory.id == factory_id).first()
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Factory not found",
        )

    llm = initialize_groq_llm()
    if llm is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GROQ_API_KEY or Groq dependencies are not configured",
        )

    factory_context = build_ai_tool_context(db, factory_id)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a professional factory supervisor for a multi-tenant Factory ERP SaaS. "
                "Use only the provided factory context for inventory, machines, customers, and production facts. "
                "Be concise, practical, and action-oriented. If the user writes Hindi or Hinglish, reply naturally in Hindi/Hinglish. "
                "Never invent stock, customer, or production data that is not present in the context.\n\n"
                "Factory context:\n{factory_context}",
            ),
            ("human", "{user_message}"),
        ]
    )
    chain = prompt | llm

    try:
        result = chain.invoke(
            {
                "factory_context": factory_context,
                "user_message": payload.user_message.strip(),
            }
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Groq supervisor response failed: {exc}",
        ) from exc

    response_text = getattr(result, "content", str(result)).strip()
    return N8NAIWebhookResponse(response=response_text)
