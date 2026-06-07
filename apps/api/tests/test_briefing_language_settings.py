import pytest
from pydantic import ValidationError

from auth import UserProfileUpdateRequest, update_user_profile
from models import User
from tests.briefing_test_utils import make_briefing_db, seed_two_factories


def test_owner_preferred_language_is_persisted():
    engine, db = make_briefing_db()
    try:
        owner, _ = seed_two_factories(db)
        owner.phone_number = "+919876543210"
        owner.phone_number_normalized = "+919876543210"
        db.commit()

        response = update_user_profile(
            UserProfileUpdateRequest(
                full_name=owner.full_name,
                country_code="+91",
                phone_number="9876543210",
                preferred_language="hi",
            ),
            current_user=owner,
            db=db,
        )

        db.expire_all()
        stored = db.query(User).filter(User.id == owner.id).one()
        assert response.preferred_language == "hi"
        assert stored.preferred_language == "hi"
    finally:
        db.close()
        engine.dispose()


def test_invalid_preferred_language_is_rejected():
    with pytest.raises(ValidationError):
        UserProfileUpdateRequest(
            full_name="Owner",
            country_code="+91",
            phone_number="9876543210",
            preferred_language="fr",
        )
