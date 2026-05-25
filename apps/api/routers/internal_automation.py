import os
import logging
import gspread
from fastapi import APIRouter, Depends, Header, HTTPException, status, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from google.oauth2.service_account import Credentials

from db import get_db
from models import Factory, FactoryAutomationSheet

# Setup Logger
logger = logging.getLogger("internal_automation")
logger.setLevel(logging.INFO)

# Router initialization
router = APIRouter(prefix="/api/internal", tags=["internal_automation"])

# ==================== AUTHENTICATION GUARD DEPENDENCY ====================
def verify_internal_auth(
    x_internal_token: Optional[str] = Header(default=None),
    x_n8n_api_key: Optional[str] = Header(default=None)
) -> None:
    """
    Strict security check validating that request originates from an internal 
    cron worker or n8n workflow system. Checks both dedicated internal token 
    and n8n api key environment configs.
    """
    expected_internal_token = os.getenv("INTERNAL_API_TOKEN")
    expected_n8n_api_key = os.getenv("N8N_API_KEY")

    # Match token values securely
    is_valid = False
    if expected_internal_token and x_internal_token == expected_internal_token:
        is_valid = True
    elif expected_n8n_api_key and x_n8n_api_key == expected_n8n_api_key:
        is_valid = True
        
    # Support development fallback if no tokens are configured in host environment
    if not expected_internal_token and not expected_n8n_api_key:
        logger.warning("No security tokens configured in environment. Access allowed in dev fallback mode.")
        is_valid = True

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access Denied: Invalid internal token or credentials"
        )

# ==================== PYDANTIC MODELS ====================
class AutomationSheetRegister(BaseModel):
    factory_id: int = Field(..., description="Target factory ID mapping")
    sheet_name: str = Field(..., min_length=1, max_length=255, description="Logical name of the sheet configuration")
    sheet_type: str = Field("cron_automation", max_length=50, description="Category type of automation")
    google_sheet_url: Optional[str] = Field(None, max_length=500, description="Full spreadsheet URL (optional)")
    google_sheet_id: str = Field(..., min_length=1, max_length=255, description="Google Spreadsheet unique ID hash")
    is_active: bool = Field(True, description="Active status identifier")

class AutomationSheetResponse(BaseModel):
    id: int
    factory_id: int
    sheet_name: str
    sheet_type: str
    google_sheet_id: str
    is_active: bool

# ==================== ROUTES IMPLEMENTATION ====================

@router.post(
    "/automation-sheet", 
    response_model=AutomationSheetResponse, 
    dependencies=[Depends(verify_internal_auth)]
)
def register_or_update_automation_sheet(
    payload: AutomationSheetRegister,
    db: Session = Depends(get_db)
):
    """
    Registers a new private Google Sheet mapping or updates an existing mapping
    for a specific factory. (Internal Admin/n8n only).
    """
    # 1. Assert factory exists
    factory = db.query(Factory).filter(Factory.id == payload.factory_id).first()
    if not factory:
        raise HTTPException(
            status_code=404,
            detail=f"Factory ID {payload.factory_id} not found"
        )

    # 2. Check for existing mapping of same type
    existing = db.query(FactoryAutomationSheet).filter(
        FactoryAutomationSheet.factory_id == payload.factory_id,
        FactoryAutomationSheet.sheet_type == payload.sheet_type
    ).first()

    if existing:
        logger.info(f"Updating existing automation mapping for factory {payload.factory_id}")
        existing.sheet_name = payload.sheet_name
        existing.google_sheet_url = payload.google_sheet_url
        existing.google_sheet_id = payload.google_sheet_id
        existing.is_active = payload.is_active
        db.commit()
        db.refresh(existing)
        return existing
    else:
        logger.info(f"Registering fresh automation mapping for factory {payload.factory_id}")
        new_mapping = FactoryAutomationSheet(
            factory_id=payload.factory_id,
            sheet_name=payload.sheet_name,
            sheet_type=payload.sheet_type,
            google_sheet_url=payload.google_sheet_url,
            google_sheet_id=payload.google_sheet_id,
            is_active=payload.is_active
        )
        db.add(new_mapping)
        db.commit()
        db.refresh(new_mapping)
        return new_mapping

@router.get(
    "/factories/{factory_id}/automation-sheet",
    response_model=AutomationSheetResponse,
    dependencies=[Depends(verify_internal_auth)]
)
def get_automation_sheet_metadata(
    factory_id: int,
    sheet_type: str = Query("cron_automation", max_length=50),
    db: Session = Depends(get_db)
):
    """
    Retrieves the private Google Sheet tracking details for a specific factory.
    (Internal Admin/n8n only).
    """
    mapping = db.query(FactoryAutomationSheet).filter(
        FactoryAutomationSheet.factory_id == factory_id,
        FactoryAutomationSheet.sheet_type == sheet_type,
        FactoryAutomationSheet.is_active == True
    ).first()

    if not mapping:
        raise HTTPException(
            status_code=404,
            detail=f"Active automation sheet configuration of type '{sheet_type}' not found for factory {factory_id}"
        )
    return mapping

@router.get(
    "/factories/{factory_id}/automation-sheet-data",
    dependencies=[Depends(verify_internal_auth)]
)
def get_automation_sheet_data(
    factory_id: int,
    sheet_type: str = Query("cron_automation", max_length=50),
    worksheet_name: Optional[str] = Query(None, description="Target worksheet tab name (defaults to first worksheet)"),
    db: Session = Depends(get_db)
):
    """
    Dynamically connects to the private Google Sheet mapped to the factory
    using the backend's Google Service Account, and returns all records as raw JSON.
    (Internal Admin/n8n only).
    """
    # 1. Fetch Mapping metadata
    mapping = db.query(FactoryAutomationSheet).filter(
        FactoryAutomationSheet.factory_id == factory_id,
        FactoryAutomationSheet.sheet_type == sheet_type,
        FactoryAutomationSheet.is_active == True
    ).first()

    if not mapping:
        raise HTTPException(
            status_code=404,
            detail=f"Active automation configuration of type '{sheet_type}' not found for factory {factory_id}"
        )

    # 2. Initialize gspread and fetch spreadsheet records
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if not creds_path:
            creds_path = os.path.join(base_dir, "config", "google_service_account.json")
            
        if not os.path.exists(creds_path):
            raise FileNotFoundError("Google credentials configuration asset map missing.")
            
        credentials = Credentials.from_service_account_file(creds_path, scopes=scopes)
        client = gspread.authorize(credentials)
        
        # Safe logging (obscuring sheet id)
        obscured_id = mapping.google_sheet_id[:6] + "..." + mapping.google_sheet_id[-6:] if len(mapping.google_sheet_id) > 12 else "..."
        logger.info(f"Dynamically loading data from spreadsheet ID: {obscured_id}")
        
        spreadsheet = client.open_by_key(mapping.google_sheet_id)
        
        # Target worksheet resolution
        if worksheet_name:
            worksheet = spreadsheet.worksheet(worksheet_name)
        else:
            worksheet = spreadsheet.get_worksheet(0)
            
        # Get all records as dictionary lists
        records = worksheet.get_all_records()
        logger.info(f"Successfully retrieved {len(records)} records from sheet.")
        
        return {
            "factory_id": factory_id,
            "sheet_name": mapping.sheet_name,
            "sheet_type": sheet_type,
            "worksheet_name": worksheet.title,
            "data": records
        }
    except gspread.exceptions.SpreadsheetNotFound:
        raise HTTPException(
            status_code=404,
            detail="Mapped Google Spreadsheet was not found. Please verify that the sheet ID is correct."
        )
    except gspread.exceptions.APIError as ae:
        raise HTTPException(
            status_code=502,
            detail=f"Google Sheets API response error: {str(ae)}"
        )
    except Exception as e:
        logger.exception(f"Internal automation spreadsheet fetch failure: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal automation sheet data extraction failed: {str(e)}"
        )
