from decimal import Decimal
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base, get_db
from models import Factory, FactoryExpense, Machine
from main import app as main_app
from auth import get_current_user

def _test_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()

def test_expense_with_machine_id_regression():
    db = _test_db()
    
    # Setup Factory and Machine
    f = Factory(id=1, name="Test Factory")
    db.add(f)
    db.flush()
    
    m = Machine(id=42, factory_id=1, name="Cup Maker 5000", machine_type="Paper Cup Machine")
    db.add(m)
    db.flush()
    db.commit()

    client = TestClient(main_app)
    mock_user = SimpleNamespace(id=1, factory_id=1, role="Owner", is_active=True, full_name="Owner User", username="owner")
    
    # Apply dependency overrides
    main_app.dependency_overrides[get_current_user] = lambda: mock_user
    main_app.dependency_overrides[get_db] = lambda: db

    try:
        # 1. Create expense with machine_id
        payload = {
            "expense_name": "Greasing machine parts",
            "amount": 1500.00,
            "category": "Maintenance",
            "machine_id": 42
        }
        res_post = client.post("/api/expenses", json=payload)
        assert res_post.status_code == 201
        data_post = res_post.json()
        assert data_post["expense_name"] == "Greasing machine parts"
        assert data_post["amount"] == "1500.00"
        assert data_post["category"] == "Maintenance"
        assert data_post["machine_id"] == 42

        # 2. List expenses and verify the machine_id is included
        res_get = client.get("/api/expenses")
        assert res_get.status_code == 200
        data_get = res_get.json()
        assert len(data_get) > 0
        assert data_get[0]["machine_id"] == 42
        assert data_get[0]["expense_name"] == "Greasing machine parts"
        
    finally:
        main_app.dependency_overrides.pop(get_current_user, None)
        main_app.dependency_overrides.pop(get_db, None)
