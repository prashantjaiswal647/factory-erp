from datetime import datetime, timedelta, timezone

from auth import resolve_factory_subscription
from models import Factory


def test_active_cashfree_period_allows_access():
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    factory = Factory(
        name="Cashfree Active Factory",
        subscription_status="active",
        payment_status="paid",
        current_period_end=expires_at,
    )

    resolved = resolve_factory_subscription(factory)

    assert resolved["access_allowed"] is True
    assert resolved["effective_status"] == "active"
    assert resolved["subscription_end_date"] == expires_at


def test_cashfree_trial_end_is_treated_as_active_trial():
    trial_end = datetime.now(timezone.utc) + timedelta(days=7)
    factory = Factory(
        name="Cashfree Trial Factory",
        subscription_status="trial_active",
        payment_status="payment_pending",
        trial_end=trial_end,
    )

    resolved = resolve_factory_subscription(factory)

    assert resolved["access_allowed"] is True
    assert resolved["effective_status"] == "trial_active"
    assert resolved["trial_end_date"] == trial_end


def test_expired_cashfree_period_denies_access():
    expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    factory = Factory(
        name="Cashfree Expired Factory",
        subscription_status="active",
        payment_status="paid",
        current_period_end=expires_at,
    )

    resolved = resolve_factory_subscription(factory)

    assert resolved["access_allowed"] is False
    assert resolved["effective_status"] == "expired"
    assert resolved["subscription_end_date"] == expires_at
