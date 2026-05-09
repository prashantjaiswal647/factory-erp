import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


CURRENT_FILE = Path(__file__).resolve()
ENV_PATHS = [CURRENT_FILE.parent / ".env"]
if len(CURRENT_FILE.parents) > 2:
    ENV_PATHS.append(CURRENT_FILE.parents[2] / ".env")

for env_path in ENV_PATHS:
    if env_path.exists():
        load_dotenv(env_path)
        break

POSTGRES_DB = os.getenv("POSTGRES_DB", "ai_erp")
POSTGRES_USER = os.getenv("POSTGRES_USER", "erp_admin")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", os.getenv("POSTGRES_PORT", "5432"))

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{DB_HOST}:{DB_PORT}/{POSTGRES_DB}",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
