from db import SessionLocal
from models import (
    BlankStock, BottomStock, BoxStock, PlasticStock, PolybagStock,
    FinalProductStock, FinishedGoodsStock, Inventory, PackagingProfile,
    ActivityLog
)
from sqlalchemy import text
import json

db = SessionLocal()
factory_id = 187

tables = {
    "blank_stock": BlankStock,
    "bottom_stock": BottomStock,
    "box_stock": BoxStock,
    "plastic_stock": PlasticStock,
    "polybag_stock": PolybagStock,
    "final_product_stock": FinalProductStock,
    "finished_goods_stock": FinishedGoodsStock,
    "inventory": Inventory,
    "packaging_profile": PackagingProfile
}

try:
    print(f"--- PILOT AUDIT DATA FOR FACTORY {factory_id} ---")
    for name, model in tables.items():
        query = db.query(model).filter(model.factory_id == factory_id)
        count = query.count()
        print(f"\nTable '{name}': {count} rows")
        rows = query.limit(10).all()
        for i, row in enumerate(rows):
            # Convert row to dict of attributes for easy inspection
            attrs = {c.name: getattr(row, c.name) for c in row.__table__.columns}
            print(f"  Row {i+1}: {attrs}")
            
    # Pull latest bulk upload logs
    print("\n--- LATEST ONBOARDING RUN ACTIVITY LOGS ---")
    logs = (
        db.query(ActivityLog)
        .filter(ActivityLog.factory_id == factory_id)
        .order_by(ActivityLog.id.desc())
        .limit(10)
        .all()
    )
    for log in logs:
        print(f"Log ID: {log.id}, Event: {log.event_type}, Action: {log.action_type}, CreatedAt: {log.created_at}, Description: {log.description}")
        
except Exception as e:
    import traceback
    print("Error pulling data:")
    traceback.print_exc()
finally:
    db.close()
