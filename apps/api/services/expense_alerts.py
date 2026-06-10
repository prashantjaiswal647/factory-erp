from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict
from sqlalchemy.orm import Session
from sqlalchemy import func
from models import FactoryExpense, UnifiedAlert, Machine
from services.telegram_bot import send_telegram_message

EXPENSE_CATEGORIES = [
    "Electricity", "Diesel", "Transport", "Mobil oil", 
    "Paraffin oil", "Repair", "Salary advance", "Packing misc", "Other"
]

def analyze_expense_leaks(db: Session, factory_id: int):
    """
    Analyzes expenses for a factory and generates alerts based on cost leakage rules.
    """
    today = datetime.utcnow().date()
    seven_days_ago = today - timedelta(days=7)
    
    # 1. Daily expense above 7-day average by 20%
    total_today = db.query(func.sum(FactoryExpense.amount))\
        .filter(FactoryExpense.factory_id == factory_id, 
                func.date(FactoryExpense.timestamp) == today).scalar() or 0
    
    avg_7_days = db.query(func.avg(
        db.query(func.sum(FactoryExpense.amount))
        .filter(FactoryExpense.factory_id == factory_id, 
                func.date(FactoryExpense.timestamp) == func.date(FactoryExpense.timestamp))
        .group_by(func.date(FactoryExpense.timestamp))
        .subquery()
    )).filter(func.date(FactoryExpense.timestamp) >= seven_days_ago).scalar() or 0
    
    # Simplified average for logic: total last 7 days / 7
    total_7_days = db.query(func.sum(FactoryExpense.amount))\
        .filter(FactoryExpense.factory_id == factory_id, 
                func.date(FactoryExpense.timestamp) >= seven_days_ago,
                func.date(FactoryExpense.timestamp) < today).scalar() or 0
    
    daily_avg = total_7_days / 7 if total_7_days > 0 else 0
    
    if daily_avg > 0 and total_today > daily_avg * 1.2:
        create_leak_alert(db, factory_id, "Cost Spike", 
                          f"Today's total expense ₹{total_today:,.2f} is 20% above 7-day avg (₹{daily_avg:,.2f})", 
                          "WARNING")

    # 2. Category-specific spikes (Electricity, Transport)
    for cat in ["Electricity", "Transport"]:
        cat_today = db.query(func.sum(FactoryExpense.amount))\
            .filter(FactoryExpense.factory_id == factory_id, 
                    FactoryExpense.category == cat, 
                    func.date(FactoryExpense.timestamp) == today).scalar() or 0
            
        cat_avg = db.query(func.sum(FactoryExpense.amount))\
            .filter(FactoryExpense.factory_id == factory_id, 
                    FactoryExpense.category == cat, 
                    func.date(FactoryExpense.timestamp) >= seven_days_ago,
                    func.date(FactoryExpense.timestamp) < today).scalar() or 0
        cat_daily_avg = cat_avg / 7 if cat_avg > 0 else 0
        
        if cat_daily_avg > 0 and cat_today > cat_daily_avg * 1.3: # 30% spike for specific categories
            create_leak_alert(db, factory_id, f"{cat} Spike", 
                              f"{cat} cost today ₹{cat_today:,.2f} spiked compared to avg ₹{cat_daily_avg:,.2f}", 
                              "WARNING")

    # 3. Repeat Repair on same machine
    # Check if same machine had 'Repair' category expense in last 3 days
    recent_repairs = db.query(FactoryExpense)\
        .filter(FactoryExpense.factory_id == factory_id, 
                FactoryExpense.category == "Repair", 
                FactoryExpense.timestamp >= (datetime.utcnow() - timedelta(days=3)))\
        .all()
    
    machine_repair_counts = {}
    for r in recent_repairs:
        if r.machine_id:
            machine_repair_counts[r.machine_id] = machine_repair_counts.get(r.machine_id, 0) + 1
            
    for m_id, count in machine_repair_counts.items():
        if count > 1:
            machine = db.query(Machine).filter(Machine.id == m_id).first()
            m_name = machine.name if machine else f"ID {m_id}"
            create_leak_alert(db, factory_id, "Repeated Repair", 
                              f"Machine {m_name} has been repaired {count} times in 3 days. Potential quality issue.", 
                              "CRITICAL")

def create_leak_alert(db: Session, factory_id: int, title: str, message: str, severity: str):
    dedupe_key = f"leak_{title.lower().replace(' ', '_')}"
    
    # Update or Create UnifiedAlert
    alert = db.query(UnifiedAlert).filter(
        UnifiedAlert.factory_id == factory_id, 
        UnifiedAlert.dedupe_key == dedupe_key
    ).first()
    
    if alert:
        alert.message = message
        alert.last_detected_at = datetime.utcnow()
        alert.status = "OPEN"
    else:
        alert = UnifiedAlert(
            factory_id=factory_id,
            dedupe_key=dedupe_key,
            title=title,
            message=message,
            severity=severity,
            source_module="expenses",
            assigned_role="Owner"
        )
        db.add(alert)
    
    db.commit()
    # Trigger Telegram alert
    send_telegram_message(factory_id, f"⚠️ {title}: {message}")
