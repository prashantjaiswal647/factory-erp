from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db import Base
from models import Factory, FinalProductStock, PackagingMetrics
from tools.dedupe_t1_2 import run_dedupe


def make_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    session.add_all([Factory(id=1, name="Factory One"), Factory(id=2, name="Factory Two")])
    session.commit()
    return session


def seed_duplicates(session):
    session.add_all(
        [
            FinalProductStock(
                factory_id=1,
                product_size_ml=250,
                variety="Standard/White",
                packaging_size_name="Box A",
                pieces_per_packet=50,
                current_quantity=500,
                total_boxes=1,
                loose_packets=2,
                packets_per_box_limit=10,
            ),
            FinalProductStock(
                factory_id=1,
                product_size_ml=250,
                variety=" standard/white ",
                packaging_size_name="box a",
                pieces_per_packet=60,
                current_quantity=1000,
                total_boxes=2,
                loose_packets=3,
                packets_per_box_limit=12,
            ),
            FinalProductStock(
                factory_id=2,
                product_size_ml=250,
                variety="Standard/White",
                packaging_size_name="Box A",
                pieces_per_packet=50,
                current_quantity=700,
                total_boxes=1,
                loose_packets=0,
                packets_per_box_limit=10,
            ),
            PackagingMetrics(
                factory_id=1,
                cup_size_ml=250,
                variant_name="Printed",
                kg_per_box=Decimal("4.500"),
                cups_per_box=500,
            ),
            PackagingMetrics(
                factory_id=1,
                cup_size_ml=250,
                variant_name=" printed ",
                kg_per_box=Decimal("4.750"),
                cups_per_box=550,
            ),
            PackagingMetrics(
                factory_id=2,
                cup_size_ml=250,
                variant_name="Printed",
                kg_per_box=Decimal("5.000"),
                cups_per_box=600,
            ),
        ]
    )
    session.commit()


def test_dry_run_reports_duplicates_without_mutation():
    session = make_session()
    try:
        seed_duplicates(session)
        report = run_dedupe(session)

        assert report["mode"] == "dry-run"
        assert report["total_duplicate_count"] == 2
        assert report["tables"]["final_product_stock"]["duplicate_count"] == 1
        assert report["tables"]["packaging_metrics"]["duplicate_count"] == 1
        assert report["tables"]["final_product_stock"]["affected_keys"][0]["key"]["factory_id"] == 1
        assert report["tables"]["packaging_metrics"]["affected_keys"][0]["suggested_merge"]["conflicts"]
        assert session.query(FinalProductStock).count() == 3
        assert session.query(PackagingMetrics).count() == 3
    finally:
        session.close()


def test_apply_merges_deterministically_and_preserves_other_factory():
    session = make_session()
    try:
        seed_duplicates(session)
        report = run_dedupe(session, apply=True)

        assert report["mode"] == "apply"
        assert report["applied_duplicate_count"] == 2

        factory_one_stock = (
            session.query(FinalProductStock)
            .filter(FinalProductStock.factory_id == 1)
            .one()
        )
        assert factory_one_stock.current_quantity == 1500
        assert factory_one_stock.total_boxes == 3
        assert factory_one_stock.loose_packets == 5
        assert factory_one_stock.pieces_per_packet == 60
        assert factory_one_stock.packets_per_box_limit == 12

        factory_one_metric = (
            session.query(PackagingMetrics)
            .filter(PackagingMetrics.factory_id == 1)
            .one()
        )
        assert factory_one_metric.kg_per_box == Decimal("4.750")
        assert factory_one_metric.cups_per_box == 550

        assert session.query(FinalProductStock).filter(FinalProductStock.factory_id == 2).count() == 1
        assert session.query(PackagingMetrics).filter(PackagingMetrics.factory_id == 2).count() == 1
    finally:
        session.close()
