from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from db import get_db
from routers.super_admin import no_store, require_super_admin
from services.briefing_observability import briefing_logs, briefing_overview, cost_spike_events, factory_health


router = APIRouter(
    prefix="/api/admin/briefings",
    tags=["briefing-admin"],
    dependencies=[Depends(require_super_admin)],
)


@router.get("/overview")
def overview(response: Response, db: Session = Depends(get_db)):
    no_store(response)
    return briefing_overview(db)


@router.get("/logs")
def logs(
    response: Response,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    factory_id: int | None = Query(None, ge=1),
    briefing_date: date | None = None,
    status: Literal["generated", "sent", "failed", "skipped"] | None = None,
    db: Session = Depends(get_db),
):
    no_store(response)
    return briefing_logs(
        db,
        page=page,
        page_size=page_size,
        factory_id=factory_id,
        briefing_date=briefing_date,
        status=status,
    )


@router.get("/factory-health")
def health(
    response: Response,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    no_store(response)
    return factory_health(db, page=page, page_size=page_size)


@router.get("/cost-spikes")
def cost_spikes(
    response: Response,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    factory_id: int | None = Query(None, ge=1),
    snapshot_date: date | None = None,
    status: Literal["generated", "sent", "failed", "skipped"] | None = None,
    db: Session = Depends(get_db),
):
    no_store(response)
    return cost_spike_events(
        db,
        page=page,
        page_size=page_size,
        factory_id=factory_id,
        snapshot_date=snapshot_date,
        status=status,
    )
