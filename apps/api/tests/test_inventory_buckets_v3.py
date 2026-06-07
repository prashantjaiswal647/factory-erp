from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import (
    BlankStock,
    BottomStock,
    BoxStock,
    Factory,
    FinalProductStock,
    Inventory,
    PlasticStock,
    PolybagStock,
)
from routers.inventory import list_live_stock


def test_live_inventory_v3_buckets_and_factory_isolation():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        factory_a = Factory(name="Inventory V3 Factory A")
        factory_b = Factory(name="Inventory V3 Factory B")
        db.add_all([factory_a, factory_b])
        db.flush()

        db.add_all(
            [
                Inventory(factory_id=factory_a.id, item_name="Raw Adhesive", category="Raw", unit="kg", quantity=20),
                Inventory(factory_id=factory_a.id, item_name="Packing Tape", category="Packaging", unit="pieces", quantity=30),
                Inventory(factory_id=factory_a.id, item_name="Legacy Unmapped", category=None, unit="pieces", quantity=2),
                BlankStock(factory_id=factory_a.id, blank_size_ml=100, variety="White", linked_bottom_size_mm=65, total_qty_kg=40),
                BottomStock(factory_id=factory_a.id, bottom_size_mm=65, variety="White", total_rolls=12, total_weight_kg=25, total_qty_kg=25),
                BoxStock(factory_id=factory_a.id, packaging_size_name="100ml Box", box_type="5 Ply", quantity=15),
                PlasticStock(factory_id=factory_a.id, plastic_size_name="100ml Sleeve", cup_size_ml=100, total_boras=2, weight_per_bora_kg=10),
                PolybagStock(factory_id=factory_a.id, packaging_size_name="100ml Polybag", total_packets=20),
                FinalProductStock(
                    factory_id=factory_a.id,
                    product_size_ml=100,
                    variety="White",
                    packaging_size_name="100ml Box",
                    pieces_per_packet=100,
                    current_quantity=4,
                    total_boxes=4,
                    loose_packets=0,
                    packets_per_box_limit=10,
                ),
                Inventory(factory_id=factory_b.id, item_name="Other Factory Raw", category="Raw", unit="kg", quantity=99),
            ]
        )
        db.commit()

        response = list_live_stock(current_user=SimpleNamespace(factory_id=factory_a.id), db=db)
        by_name = {row["item_name"]: row for row in response}

        assert len(response) == 9
        assert {row["factory_id"] for row in response} == {factory_a.id}
        assert by_name["Raw Adhesive"]["bucket"] == "raw_other"
        assert by_name["Packing Tape"]["bucket"] == "polybags_packing"
        assert by_name["Legacy Unmapped"]["bucket"] == "needs_mapping_review"
        assert "Other Factory Raw" not in by_name
        assert all(row["stock_type"] not in {"Raw", "Packaging"} for row in response)
        assert {row["bucket"] for row in response} == {
            "cup_blanks",
            "bottom_reels",
            "boxes",
            "polybags_packing",
            "finished_goods",
            "raw_other",
            "needs_mapping_review",
        }
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
