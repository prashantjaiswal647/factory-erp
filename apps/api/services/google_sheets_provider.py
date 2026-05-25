import os
import logging
from google.oauth2.service_account import Credentials
import gspread
from fastapi import HTTPException

# Configure Logger
logger = logging.getLogger("google_sheets_provider")
logger.setLevel(logging.INFO)

# Ensure handlers exist
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

def initialize_factory_google_sheet(factory_id: str, owner_email: str = None) -> str:
    """
    Autonomous spreadsheet layout initialization wrapper engine.
    Creates 7 synchronized operational tabs matching factory id specifications.
    """
    logger.info(f"Starting Google Sheet initialization for Factory ID: {factory_id}")
    try:
        # Load centralized Cloud Console JSON credentials safely
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        # Robust path resolution
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # apps/api
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if not creds_path:
            creds_path = os.path.join(base_dir, "config", "google_service_account.json")
            
        logger.info(f"Resolving Google Service Account credentials at path: {creds_path}")
        if not os.path.exists(creds_path):
            raise FileNotFoundError(f"Google credentials configuration asset map missing at {creds_path}")
            
        credentials = Credentials.from_service_account_file(creds_path, scopes=scopes)
        client = gspread.authorize(credentials)
        
        # Step A: Dynamic Multi-tenant Sheet Title Generation
        sheet_title = f"Factory_Sheet_{factory_id}"
        logger.info(f"Creating Spreadsheet named: '{sheet_title}'")
        spreadsheet = client.create(sheet_title)
        
        # Step B: Define target workflows structural tabs mapping with precise system headers
        tabs_config = {
            "Workers": ["id", "name", "salary", "duty_hours", "shift_type"],
            "Machines": ["id", "machine_number", "machine_type", "mould_size_ml", "speed_bpm"],
            "Customers": ["id", "name", "phone", "balance_amount", "firm_name", "is_active"],
            "Raw_Material": ["id", "name", "material_type", "current_stock", "price_per_unit"],
            "Production": ["id", "date", "machine_id", "boxes_produced", "wastage_kg", "status"],
            "Sales": ["id", "date", "customer_name", "box_quantity", "total_amount", "amount_paid"],
            "Outstanding_Payments": ["id", "customer_name", "contact", "total_due", "last_reminder_date"]
        }
        
        # Step C: Loop structural injection vectors
        for tab_name, headers in tabs_config.items():
            # Pehle default generated sheet1 tab context standard ko verify match reuse karein
            if tab_name == "Workers":
                worksheet = spreadsheet.get_worksheet(0)
                worksheet.update_title("Workers")
            else:
                worksheet = spreadsheet.add_worksheet(title=tab_name, rows="1000", cols="20")
            
            logger.info(f"Appending headers to Worksheet: '{tab_name}'")
            # Master headers tracking layout configuration flush karein
            worksheet.append_row(headers)
            
        # Security permissions step: n8n server proxy account ko permission read/write allow karein
        developer_email = os.getenv("DEVELOPER_SYSTEM_EMAIL", "n8n-munshiai@serviceaccount.com")
        logger.info(f"Sharing Spreadsheet with: '{developer_email}' as Writer")
        spreadsheet.share(developer_email, perm_type='user', role='writer')
        
        # Share with Factory Owner if their email exists
        if owner_email:
            logger.info(f"Sharing Spreadsheet with Factory Owner: '{owner_email}' as Writer")
            try:
                spreadsheet.share(owner_email, perm_type='user', role='writer')
            except Exception as se:
                logger.warning(f"Could not share sheet with owner email '{owner_email}': {str(se)}")
        
        spreadsheet_id = spreadsheet.id
        logger.info(f"Google Sheet '{sheet_title}' initialized successfully with ID: '{spreadsheet_id}'")
        
        # Return unique spreadsheet tracking hash ID string to database layer logs
        return spreadsheet_id
    except Exception as e:
        logger.exception(f"Google cloud sheets engine allocation failure: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Google cloud sheets engine allocation failure: {str(e)}")

def initialize_factory_google_sheet_task(factory_id: int):
    """
    Background worker task to initialize Google Sheet for a factory
    and save the sheet ID to the database.
    """
    from db import SessionLocal
    from models import Factory, User
    
    logger.info(f"Background task triggered to initialize Google Sheet for Factory ID: {factory_id}")
    db = SessionLocal()
    try:
        # Get factory owner's email
        factory = db.query(Factory).filter(Factory.id == factory_id).first()
        owner_email = None
        if factory and factory.owner_id:
            owner = db.query(User).filter(User.id == factory.owner_id).first()
            if owner and owner.username and "@" in owner.username:
                owner_email = owner.username.strip()
                logger.info(f"Found factory owner email: {owner_email}")

        sheet_id = initialize_factory_google_sheet(str(factory_id), owner_email=owner_email)
        
        # Update factory with google_sheet_id
        if factory:
            factory.google_sheet_id = sheet_id
            db.commit()
            logger.info(f"Successfully recorded Google Sheet ID '{sheet_id}' for factory {factory_id} in DB.")
        else:
            logger.error(f"Factory ID {factory_id} not found in DB during google_sheet_id write.")
    except Exception as e:
        db.rollback()
        logger.error(f"Background task failed to initialize Google Sheet for factory {factory_id}: {str(e)}")
    finally:
        db.close()
