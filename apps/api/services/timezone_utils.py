import datetime

try:
    from zoneinfo import ZoneInfo
    KOLKATA_ZONE = ZoneInfo("Asia/Kolkata")
except Exception:
    # Fallback to fixed offset of UTC+5:30 if zoneinfo isn't populated on slim container
    KOLKATA_ZONE = datetime.timezone(datetime.timedelta(hours=5, minutes=30), name="Asia/Kolkata")

def get_kolkata_now() -> datetime.datetime:
    return datetime.datetime.now(KOLKATA_ZONE)

def get_kolkata_today() -> datetime.date:
    return get_kolkata_now().date()

def get_kolkata_yesterday() -> datetime.date:
    return get_kolkata_today() - datetime.timedelta(days=1)
