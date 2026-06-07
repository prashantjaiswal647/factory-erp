import time
import logging
import sys
import os

# Adjust path to import from parent directory if needed
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import SessionLocal
from services.telegram_action_session import expire_sessions
from services.telegram_callback_dedupe import cleanup_callback_dedupes

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("telegram_session_cleaner")

def main():
    logger.info("Telegram Action Session cleaner started.")
    while True:
        try:
            db = SessionLocal()
            try:
                expire_sessions(db)
                cleanup_callback_dedupes(db)
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error in cleaner loop: {e}", exc_info=True)
        time.sleep(60)

if __name__ == "__main__":
    main()
