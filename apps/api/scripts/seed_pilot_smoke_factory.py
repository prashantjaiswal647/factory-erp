#!/usr/bin/env python3
"""
Deterministic seed script for pilot smoke test.
Creates/updates test factory with email: test42@munshi-ai.example.com
MUST set ALLOW_TEST_SEED=true to run.
Idempotent: safe to run multiple times.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import from db, auth, models
from db import SessionLocal
from auth import hash_password
from models import Factory, User

# Test factory credentials (deterministic)
TEST_EMAIL = 'test42@munshi-ai.example.com'
TEST_PASSWORD = 'Test@123456'
TEST_PHONE = '+919999999942'
TEST_FACTORY_NAME = 'Munshi Test Factory'
TEST_OWNER_NAME = 'Test Owner 42'

def seed():
    db = SessionLocal()
    try:
        # 1. Create or update Factory
        factory = db.query(Factory).filter(Factory.name == TEST_FACTORY_NAME).first()
        now = datetime.now(timezone.utc)
        if not factory:
            print(f'Creating test factory: {TEST_FACTORY_NAME}')
            factory = Factory(
                name=TEST_FACTORY_NAME,
                factory_name=TEST_FACTORY_NAME,
                address='123 Industrial Area, Mumbai, Maharashtra - 400001',
                gst_number='27AADCB9999FZY9Z',
                trial_start_date=now,
                trial_end_date=now + timedelta(days=30),
                subscription_status='trial_active',
                active_plan='Pro Premium Suite',
                plan_name='Pro Premium Suite',
                payment_status='trial_active',
            )
            db.add(factory)
            db.commit()
            db.refresh(factory)
        else:
            print(f'Using existing factory: {factory.name}')
            factory.subscription_status = 'trial_active'
            factory.trial_end_date = now + timedelta(days=30)
            factory.active_plan = 'Pro Premium Suite'
            factory.plan_name = 'Pro Premium Suite'
            db.commit()

        # 2. Create or update User
        user = db.query(User).filter(User.username == TEST_EMAIL).first()
        if user:
            # Temporarily break circular FK references to avoid constraint violation on update
            db.query(Factory).filter(Factory.owner_phone_number == user.phone_number).update({Factory.owner_phone_number: None})
            db.query(Factory).filter(Factory.owner_id == user.id).update({Factory.owner_id: None})
            db.commit()
            
        if not user:
            print(f'Creating test user: {TEST_EMAIL}')
            user = User(
                factory_id=factory.id,
                username=TEST_EMAIL,
                email=TEST_EMAIL,
                phone_number=TEST_PHONE,
                phone_number_normalized=TEST_PHONE,
                full_name=TEST_OWNER_NAME,
                password_hash=hash_password(TEST_PASSWORD),
                role='Owner',
                is_verified=True,
                is_active=True
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            print(f'Updating existing test user: {TEST_EMAIL}')
            user.factory_id = factory.id
            user.phone_number = TEST_PHONE
            user.phone_number_normalized = TEST_PHONE
            user.is_verified = True
            user.is_active = True
            user.role = 'Owner'
            user.password_hash = hash_password(TEST_PASSWORD)
            db.commit()

        # 3. Associate Factory Owner links
        factory.owner_id = user.id
        factory.owner_phone_number = user.phone_number
        db.commit()

        # 4. Wipe out previous transactional data for this factory
        print(f"Cleaning up previous transactional data for factory_id={factory.id}...")
        from models import (
            DailyProduction, SalesInvoice, Payment, Worker, Inventory,
            OutstandingBill, InvoiceDocument, RecoveryFollowup,
            MorningBriefingLog, BriefingSnapshot, Customer, PaymentCollection, BillPayment,
            BlankStock, BottomStock, BoxStock, PlasticStock, FinishedGoodsStock, PackagingProfile, Machine,
            DailySale
        )
        
        # Delete dependent child tables first
        db.query(PaymentCollection).filter(PaymentCollection.factory_id == factory.id).delete(synchronize_session=False)
        db.query(BillPayment).filter(BillPayment.factory_id == factory.id).delete(synchronize_session=False)
        db.query(Payment).filter(Payment.factory_id == factory.id).delete(synchronize_session=False)
        db.query(DailySale).filter(DailySale.factory_id == factory.id).delete(synchronize_session=False)
        db.query(OutstandingBill).filter(OutstandingBill.factory_id == factory.id).delete(synchronize_session=False)
        db.query(InvoiceDocument).filter(InvoiceDocument.factory_id == factory.id).delete(synchronize_session=False)
        db.query(SalesInvoice).filter(SalesInvoice.factory_id == factory.id).delete(synchronize_session=False)
        db.query(DailyProduction).filter(DailyProduction.factory_id == factory.id).delete(synchronize_session=False)
        db.query(RecoveryFollowup).filter(RecoveryFollowup.factory_id == factory.id).delete(synchronize_session=False)
        db.query(MorningBriefingLog).filter(MorningBriefingLog.factory_id == factory.id).delete(synchronize_session=False)
        db.query(BriefingSnapshot).filter(BriefingSnapshot.factory_id == factory.id).delete(synchronize_session=False)
        db.query(FinishedGoodsStock).filter(FinishedGoodsStock.factory_id == factory.id).delete(synchronize_session=False)
        db.query(PackagingProfile).filter(PackagingProfile.factory_id == factory.id).delete(synchronize_session=False)
        db.query(Inventory).filter(Inventory.factory_id == factory.id).delete(synchronize_session=False)
        db.query(Worker).filter(Worker.factory_id == factory.id).delete(synchronize_session=False)
        db.query(Customer).filter(Customer.factory_id == factory.id).delete(synchronize_session=False)
        db.query(BlankStock).filter(BlankStock.factory_id == factory.id).delete(synchronize_session=False)
        db.query(BottomStock).filter(BottomStock.factory_id == factory.id).delete(synchronize_session=False)
        db.query(BoxStock).filter(BoxStock.factory_id == factory.id).delete(synchronize_session=False)
        db.query(PlasticStock).filter(PlasticStock.factory_id == factory.id).delete(synchronize_session=False)
        db.query(Machine).filter(Machine.factory_id == factory.id).delete(synchronize_session=False)
        db.commit()
        print("Cleanup completed successfully.")
        
        print(f'\nSEED COMPLETE: Factory ID={factory.id}, Owner ID={user.id}')
        print(f'  Email: {TEST_EMAIL}')
        print(f'  Password: {TEST_PASSWORD}')
        print(f'  Verified: {user.is_verified}')
        
    except Exception as e:
        db.rollback()
        print(f'ERROR: {e}')
        import traceback; traceback.print_exc()
        raise
    finally:
        db.close()

if __name__ == '__main__':
    seed()
