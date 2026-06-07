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


def test_live_inventory_buckets_and_factory_isolation():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        factory_a = Factory(name="Inventory Factory A")
        factory_b = Factory(name="Inventory Factory B")
        db.add_all([factory_a, factory_b])
        db.flush()

        db.add_all(
            [
                Inventory(factory_id=factory_a.id, item_name="Raw Adhesive", category="Raw", unit="kg", quantity=20, price_per_unit=10),
                Inventory(factory_id=factory_a.id, item_name="Packing Tape", category="Packaging", unit="pieces", quantity=30, price_per_unit=5),
                BlankStock(factory_id=factory_a.id, blank_size_ml=100, variety="White", linked_bottom_size_mm=65, total_qty_kg=40),
                BottomStock(factory_id=factory_a.id, bottom_size_mm=65, variety="White", total_rolls=12, total_weight_kg=25, total_qty_kg=25),
                BoxStock(factory_id=factory_a.id, packaging_size_name="100ml Box", box_type="5 Ply", quantity=15, price_per_box=12),
                PlasticStock(factory_id=factory_a.id, plastic_size_name="100ml Sleeve", cup_size_ml=100, total_boras=2, weight_per_bora_kg=10, price_per_kg=100),
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
                Inventory(factory_id=factory_b.id, item_name="Other Factory Raw", category="Raw", unit="kg", quantity=99, price_per_unit=1),
            ]
        )
        db.commit()

        response = list_live_stock(
            current_user=SimpleNamespace(factory_id=factory_a.id),
            db=db,
        )

        assert len(response) == 8
        assert {row["factory_id"] for row in response} == {factory_a.id}
        assert {row["bucket"] for row in response} == {
            "cup_blanks",
            "bottom_reels",
            "boxes",
            "polybags_packing",
            "finished_goods",
            "raw_other",
        }
        assert all(row["stock_type"] not in {"Raw", "Packaging"} for row in response)

        raw_row = next(row for row in response if row["item_name"] == "Raw Adhesive")
        packing_row = next(row for row in response if row["item_name"] == "Packing Tape")
        final_row = next(row for row in response if row["bucket"] == "finished_goods")
        assert raw_row["stock_type"] == "Inventory"
        assert raw_row["bucket"] == "raw_other"
        assert packing_row["stock_type"] == "Inventory"
        assert packing_row["bucket"] == "polybags_packing"
        assert final_row["category"] == "CUP_FINISHED"
        assert final_row["category"] not in {"CUP_BLANK", "CUP_BOTTOM", "PACKAGING_MATERIAL"}
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
