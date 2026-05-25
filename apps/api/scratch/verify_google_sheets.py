import os
import sys

# Ensure apps/api is in Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from sqlalchemy import create_engine, inspect
from db import DATABASE_URL, SessionLocal
from models import Factory
from services.google_sheets_provider import initialize_factory_google_sheet_task

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verify_google_sheets")

def main():
    logger.info("=== STARTING GOOGLE SHEETS ONBOARDING INTEGRATION VERIFICATION ===")
    
    # 1. Test Database Schema Migration Verification
    logger.info("1. Verifying database connection and schemas...")
    try:
        engine = create_engine(DATABASE_URL)
        inspector = inspect(engine)
        columns = inspector.get_columns("factories")
        column_names = [col["name"] for col in columns]
        
        logger.info(f"Existing columns in 'factories' table: {column_names}")
        if "google_sheet_id" in column_names:
            logger.info("SUCCESS: 'google_sheet_id' column exists in 'factories' database table.")
        else:
            logger.warning("WARNING: 'google_sheet_id' column does not exist in 'factories' database table yet. Running main.py or ensure_runtime_schema() will add it.")
    except Exception as e:
        logger.error(f"Failed to inspect database table: {str(e)}")

    # 2. Test SQLAlchemy Model attribute presence
    logger.info("\n2. Verifying SQLAlchemy Factory Model attributes...")
    if hasattr(Factory, "google_sheet_id"):
        logger.info("SUCCESS: Factory model has 'google_sheet_id' attribute mapped.")
    else:
        logger.error("ERROR: Factory model is missing the 'google_sheet_id' attribute definition.")

    # 3. Verify imports from providers and routes
    logger.info("\n3. Verifying module import paths...")
    try:
        from services.google_sheets_provider import initialize_factory_google_sheet
        logger.info("SUCCESS: 'initialize_factory_google_sheet' imported successfully.")
    except Exception as e:
        logger.error(f"ERROR: Failed to import sheets provider: {str(e)}")

    try:
        from auth import signup_json, complete_google_signup
        logger.info("SUCCESS: Auth onboarding routes imported successfully.")
    except Exception as e:
        logger.error(f"ERROR: Failed to import auth routes: {str(e)}")

    # 4. Check Service Account credentials file presence
    logger.info("\n4. Checking Google Service Account credentials file...")
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or os.path.join(base_dir, "config", "google_service_account.json")
    
    logger.info(f"Credential file path: {creds_path}")
    if os.path.exists(creds_path):
        logger.info("SUCCESS: Google credentials JSON file is present.")
    else:
        logger.warning("NOTICE: Google credentials JSON file is missing. Please make sure to download the Service Account key and place it at 'apps/api/config/google_service_account.json' for live Google sheets provisioning.")

    logger.info("\n=== VERIFICATION RUN COMPLETE ===")

if __name__ == "__main__":
    main()
