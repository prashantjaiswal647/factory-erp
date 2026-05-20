from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models import Factory, Machine


PLAN_MACHINE_LIMITS = {
    "trial": 7,
    "free": 7,
    "starter": 7,
    "active": 25,
    "growth": 25,
    "business": 100,
    "enterprise": 1000,
}


@dataclass(frozen=True)
class MachineLimitUsage:
    used: int
    limit: int
    plan: str


def get_factory_plan(db: Session, factory_id: int) -> str:
    factory = db.query(Factory).filter(Factory.id == factory_id).first()
    return (factory.subscription_status if factory else "trial") or "trial"


def get_machine_limit_for_plan(plan: str) -> int:
    return PLAN_MACHINE_LIMITS.get(plan.strip().lower(), PLAN_MACHINE_LIMITS["trial"])


def get_machine_limit_usage(db: Session, factory_id: int) -> MachineLimitUsage:
    plan = get_factory_plan(db, factory_id)
    used = db.query(Machine).filter(Machine.factory_id == factory_id).count()
    return MachineLimitUsage(used=used, limit=get_machine_limit_for_plan(plan), plan=plan)


def check_machine_limit(factory_id: int, db: Session, requested_count: int = 1) -> MachineLimitUsage:
    usage = get_machine_limit_usage(db, factory_id)
    if usage.used + requested_count > usage.limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "UPGRADE_REQUIRED",
                "message": f"You have reached your limit of {usage.limit} machines.",
                "used": usage.used,
                "limit": usage.limit,
                "plan": usage.plan,
            },
        )
    return usage
