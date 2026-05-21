import argparse
from datetime import datetime, timedelta, timezone

from db import SessionLocal
from models import Factory, User


def extend_trial(phone_number: str, days: int) -> None:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.phone_number == phone_number).first()
        if user is None:
            raise SystemExit(f"No user found for phone number: {phone_number}")

        factory = db.query(Factory).filter(Factory.id == user.factory_id).first()
        if factory is None:
            raise SystemExit(f"No factory found for user: {phone_number}")

        now = datetime.now(timezone.utc)
        factory.trial_start_date = now
        factory.trial_end_date = now + timedelta(days=days)
        factory.subscription_status = "trial_active"
        factory.payment_status = "payment_pending"
        db.commit()

        print(
            f"Extended trial for factory_id={factory.id} "
            f"until {factory.trial_end_date.isoformat()}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extend a factory trial by owner phone number.")
    parser.add_argument("--phone", required=True, help="User phone number attached to the factory")
    parser.add_argument("--days", type=int, default=30, help="Trial extension length in days")
    args = parser.parse_args()
    extend_trial(args.phone, args.days)
