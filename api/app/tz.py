"""The single timezone-conversion utility for the API. Store UTC, display/compute in business tz."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

DEFAULT_TZ = "Asia/Kolkata"


def zone(name: str | None = None) -> ZoneInfo:
    return ZoneInfo(name or DEFAULT_TZ)


def local_date(dt: datetime, tz: ZoneInfo) -> date:
    """Calendar date of an instant in the business timezone (23:30 IST belongs to that IST day)."""
    return dt.astimezone(tz).date()


def at_local(d: date, hhmm: str, tz: ZoneInfo) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return datetime.combine(d, time(h, m), tzinfo=tz)


def day_bounds(d: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(d, time(0, 0), tzinfo=tz)
    return start, datetime.combine(d + timedelta(days=1), time(0, 0), tzinfo=tz)
