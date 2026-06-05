import os
from io import BytesIO
from types import SimpleNamespace
from urllib.parse import urlparse

from fastapi import BackgroundTasks, UploadFile
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import Customer, Factory, Inventory
from routers.onboarding import get_or_create_inventory
from routers.sales import upload_customers_seed


# SQLite remains the fast default for unit coverage. Set
# P0_ISOLATION_DATABASE_URL to an isolated Postgres test database when verifying
# row locking, with_for_update, and transaction behavior before deployment.
def reset_test_schema(engine):
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
        return

    Base.metadata.drop_all(bind=engine)


def make_session():
    database_url = os.getenv("P0_ISOLATION_DATABASE_URL")
    if database_url:
        parsed = urlparse(database_url)
        database_name = parsed.path.lstrip("/").lower()
        if parsed.scheme not in {"postgresql", "postgresql+psycopg2"}:
            raise RuntimeError("P0_ISOLATION_DATABASE_URL must use PostgreSQL")
        if "test" not in database_name and "validate" not in database_name:
            raise RuntimeError("Postgres isolation tests require a database named with 'test' or 'validate'")
        engine = create_engine(database_url)
    else:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

    reset_test_schema(engine)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    session.add_all([Factory(id=1, name="Factory One"), Factory(id=2, name="Factory Two")])
    session.commit()
    session.info["test_engine"] = engine
    return session


def close_session(db):
    engine = db.info["test_engine"]
    db.close()
    reset_test_schema(engine)
    engine.dispose()


def test_customer_bulk_upload_isolation():
    db = make_session()
    try:
        db.add(
            Customer(
                factory_id=2,
                name="Other Tenant Customer",
                phone_number="9999999999",
                phone="9999999999",
            )
        )
        db.commit()

        current_user = SimpleNamespace(
            id=10,
            factory_id=1,
            username="owner1",
            full_name="Factory One Owner",
            role="Owner",
        )
        csv_data = (
            "name,phone,factory_id,place\n"
            "Uploaded Customer,9999999999,2,Delhi\n"
        ).encode()
        upload = UploadFile(file=BytesIO(csv_data), filename="customers.csv")

        result = upload_customers_seed(
            background_tasks=BackgroundTasks(),
            file=upload,
            current_user=current_user,
            db=db,
        )

        assert result["imported_count"] == 1
        uploaded = (
            db.query(Customer)
            .filter(Customer.factory_id == current_user.factory_id)
            .filter(Customer.phone_number == "9999999999")
            .one()
        )
        assert uploaded.name == "Uploaded Customer"
        assert uploaded.factory_id == 1

        other_tenant_rows = (
            db.query(Customer)
            .filter(Customer.factory_id == 2)
            .filter(Customer.phone_number == "9999999999")
            .all()
        )
        assert len(other_tenant_rows) == 1
        assert other_tenant_rows[0].name == "Other Tenant Customer"
    finally:
        close_session(db)


def test_cross_factory_get_or_create_inventory():
    db = make_session()
    try:
        other_tenant_item = Inventory(
            factory_id=2,
            item_name="250ml Carton Box",
            category="Packaging",
            unit="pieces",
            quantity=25,
            price_per_unit=5,
        )
        db.add(other_tenant_item)
        db.commit()

        current_user = SimpleNamespace(factory_id=1)
        item = get_or_create_inventory(
            db,
            current_user.factory_id,
            "250ml Carton Box",
            "Packaging",
            "pieces",
        )
        db.commit()

        assert item.factory_id == current_user.factory_id
        assert item.id != other_tenant_item.id
        assert (
            db.query(Inventory)
            .filter(Inventory.factory_id == current_user.factory_id)
            .filter(Inventory.item_name == "250ml Carton Box")
            .count()
            == 1
        )
        assert (
            db.query(Inventory)
            .filter(Inventory.factory_id == 2)
            .filter(Inventory.item_name == "250ml Carton Box")
            .count()
            == 1
        )
    finally:
        close_session(db)
