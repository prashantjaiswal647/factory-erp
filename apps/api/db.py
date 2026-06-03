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
    from services.tenant_context import clear_current_tenant_id

    clear_current_tenant_id()
    db = SessionLocal()
    try:
        yield db
    finally:
        clear_current_tenant_id()
        db.close()


# Global Tenant Query Interceptor
from sqlalchemy import event
from sqlalchemy.orm import Query

@event.listens_for(Query, "before_compile", retval=True)
def before_compile(query):
    from services.tenant_context import get_current_tenant_id
    tenant_id = get_current_tenant_id()
    if tenant_id is None:
        return query

    # Apply factory_id filter dynamically to entities that have the attribute
    for desc in query.column_descriptions:
        entity = desc.get("entity")
        if entity and hasattr(entity, "factory_id"):
            # Avoid duplicating criteria if factory_id is already filtered in the query clauses
            # SQLAlchemy handles duplicate filter conditions gracefully, but we can append it directly
            query = query.filter(entity.factory_id == tenant_id)
    return query
