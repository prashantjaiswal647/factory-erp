import os
import sys

# Ensure apps/api is in Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from sqlalchemy import create_engine, inspect
from db import DATABASE_URL
from models import FactoryAutomationSheet

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verify_internal_automation")

def main():
    logger.info("=== STARTING PRIVATE GOOGLE SHEETS AUTOMATION VERIFICATION ===")

    # 1. Test Database Schema Migration Verification
    logger.info("1. Verifying database table and column registration...")
    try:
        engine = create_engine(DATABASE_URL)
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        logger.info(f"Available tables in database: {tables}")
        
        if "factory_automation_sheets" in tables:
            logger.info("SUCCESS: 'factory_automation_sheets' table exists in database.")
            columns = inspector.get_columns("factory_automation_sheets")
            column_names = [col["name"] for col in columns]
            logger.info(f"Columns in 'factory_automation_sheets': {column_names}")
            
            required_cols = ["id", "factory_id", "sheet_name", "sheet_type", "google_sheet_url", "google_sheet_id", "is_active"]
            missing_cols = [col for col in required_cols if col not in column_names]
            if not missing_cols:
                logger.info("SUCCESS: All required columns are present in 'factory_automation_sheets' table.")
            else:
                logger.error(f"ERROR: Missing columns in table: {missing_cols}")
        else:
            logger.warning("NOTICE: 'factory_automation_sheets' table does not exist yet. Running startup migration / restarting container will trigger creation.")
    except Exception as e:
        logger.error(f"Failed to inspect database tables: {str(e)}")

    # 2. Test SQLAlchemy Model Mapping
    logger.info("\n2. Verifying SQLAlchemy FactoryAutomationSheet Model...")
    mapped_attrs = ["id", "factory_id", "sheet_name", "sheet_type", "google_sheet_url", "google_sheet_id", "is_active", "factory"]
    missing_attrs = [attr for attr in mapped_attrs if not hasattr(FactoryAutomationSheet, attr)]
    
    if not missing_attrs:
        logger.info("SUCCESS: FactoryAutomationSheet model is fully mapped with all required attributes and relationships.")
    else:
        logger.error(f"ERROR: FactoryAutomationSheet model is missing attributes: {missing_attrs}")

    # 3. Verify imports of internal automation router
    logger.info("\n3. Verifying module import paths...")
    try:
        from routers.internal_automation import router as internal_router, verify_internal_auth
        logger.info("SUCCESS: 'internal_automation' router and verify_internal_auth dependency imported cleanly.")
    except Exception as e:
        logger.error(f"ERROR: Failed to import internal automation router: {str(e)}")

    # 4. Check API secrets configuration
    logger.info("\n4. Checking API authentication secret configurations...")
    expected_internal_token = os.getenv("INTERNAL_API_TOKEN")
    expected_n8n_api_key = os.getenv("N8N_API_KEY")
    logger.info(f"INTERNAL_API_TOKEN set: {bool(expected_internal_token)}")
    logger.info(f"N8N_API_KEY set: {bool(expected_n8n_api_key)}")

    logger.info("\n=== VERIFICATION RUN COMPLETE ===")

if __name__ == "__main__":
    main()
