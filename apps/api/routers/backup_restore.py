from datetime import date
import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db import get_db
from dependencies import check_permissions
from models import Factory, User
from services.master_backup import (
    RestoreFailure,
    build_master_backup,
    build_validation_report,
    preview_backup,
    restore_staged_backup,
    stage_backup,
    staged_backup_path,
)


router = APIRouter(prefix="/api/backup", tags=["backup-restore"])


@router.get("/master")
def download_master_backup(
    current_user: User = Depends(check_permissions(["Owner"])),
    db: Session = Depends(get_db),
):
    factory = db.query(Factory).filter(Factory.id == current_user.factory_id).one()
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", factory.factory_name or factory.name).strip("_")
    filename = f"munshi_master_backup_{safe_name}_{date.today().isoformat()}.xlsx"
    return StreamingResponse(
        build_master_backup(db, int(current_user.factory_id)),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/master/validate")
async def validate_master_backup(
    file: UploadFile = File(...),
    current_user: User = Depends(check_permissions(["Owner"])),
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="Only .xlsx backup files are supported")
    file_bytes = await file.read()
    restore_id, report = stage_backup(file_bytes, int(current_user.factory_id), file.filename)
    preview = preview_backup(db, file_bytes, int(current_user.factory_id))
    return {
        "restore_id": restore_id,
        "can_restore": not report["fatal"],
        "new_records": preview["new"],
        "existing_records": preview["existing"],
        "updated_records": preview["updated"],
        "errors": report["errors"],
        "validation_report": report,
    }


class ConfirmRestoreRequest(BaseModel):
    restore_id: str
    confirmation: str


@router.get("/master/validation-report/{restore_id}")
def download_validation_report(
    restore_id: str,
    current_user: User = Depends(check_permissions(["Owner"])),
):
    path = staged_backup_path(int(current_user.factory_id), restore_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Validation upload not found")
    return StreamingResponse(
        build_validation_report(path.read_bytes(), int(current_user.factory_id)),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="master_backup_validation_report.xlsx"'},
    )


@router.post("/master/restore")
def confirm_master_restore(
    payload: ConfirmRestoreRequest,
    current_user: User = Depends(check_permissions(["Owner"])),
    db: Session = Depends(get_db),
):
    if payload.confirmation != "RESTORE":
        raise HTTPException(status_code=422, detail="Type RESTORE to confirm")
    try:
        return restore_staged_backup(db, int(current_user.factory_id), payload.restore_id)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RestoreFailure as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=exc.detail) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Restore failed and all changes were rolled back") from exc
