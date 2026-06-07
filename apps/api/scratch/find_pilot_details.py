from db import SessionLocal
from models import ActivityLog, Factory
from sqlalchemy import text

db = SessionLocal()
try:
    print("Searching activity logs...")
    logs = db.query(ActivityLog).order_by(ActivityLog.id.desc()).limit(30).all()
    for log in logs:
        print(f"ID: {log.id}, FactoryID: {log.factory_id}, Event: {log.event_type}, Action: {log.action_type}, EntityName: {log.entity_name}, EntityType: {log.entity_type}, Description: {log.description[:100]}")
    
    # Also find all factories that have some data in blank_stock
    print("\nFactories with data in blank_stock:")
    res = db.execute(text("SELECT DISTINCT factory_id FROM blank_stock")).all()
    print("  Factory IDs in blank_stock:", [r[0] for r in res])
    
    # Let's inspect the latest factory created or with active subscription
    print("\nActive/Trial factories:")
    res_factories = db.query(Factory).filter(Factory.subscription_status.in_(["active", "trial_active"])).all()
    for f in res_factories:
         print(f"  ID: {f.id}, Name: {f.name}, Status: {f.subscription_status}")
finally:
    db.close()
