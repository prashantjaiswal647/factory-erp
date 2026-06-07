import datetime
from unittest.mock import patch
from services.timezone_utils import get_kolkata_today, get_kolkata_yesterday, KOLKATA_ZONE

def test_kolkata_timezone_before_5_30_am_ist():
    # Say local time is 2026-06-06 04:00:00 IST
    # This corresponds to UTC time 2026-06-05 22:30:00 UTC
    mock_now = datetime.datetime(2026, 6, 6, 4, 0, 0, tzinfo=KOLKATA_ZONE)
    with patch("services.timezone_utils.get_kolkata_now", return_value=mock_now):
        assert get_kolkata_today() == datetime.date(2026, 6, 6)
        assert get_kolkata_yesterday() == datetime.date(2026, 6, 5)

def test_kolkata_timezone_after_5_30_am_ist():
    # Say local time is 2026-06-06 06:00:00 IST
    # This corresponds to UTC time 2026-06-06 00:30:00 UTC
    mock_now = datetime.datetime(2026, 6, 6, 6, 0, 0, tzinfo=KOLKATA_ZONE)
    with patch("services.timezone_utils.get_kolkata_now", return_value=mock_now):
        assert get_kolkata_today() == datetime.date(2026, 6, 6)
        assert get_kolkata_yesterday() == datetime.date(2026, 6, 5)

def test_kolkata_timezone_midnight_utc_edge_case():
    # UTC time is exactly 2026-06-06 00:00:00 UTC
    # Indian local time is 2026-06-06 05:30:00 IST
    mock_now = datetime.datetime(2026, 6, 6, 5, 30, 0, tzinfo=KOLKATA_ZONE)
    with patch("services.timezone_utils.get_kolkata_now", return_value=mock_now):
        assert get_kolkata_today() == datetime.date(2026, 6, 6)
        assert get_kolkata_yesterday() == datetime.date(2026, 6, 5)

def test_kolkata_timezone_just_before_midnight_utc():
    # UTC time is 2026-06-05 23:59:59 UTC
    # Indian local time is 2026-06-06 05:29:59 IST
    mock_now = datetime.datetime(2026, 6, 6, 5, 29, 59, tzinfo=KOLKATA_ZONE)
    with patch("services.timezone_utils.get_kolkata_now", return_value=mock_now):
        assert get_kolkata_today() == datetime.date(2026, 6, 6)
        assert get_kolkata_yesterday() == datetime.date(2026, 6, 5)
