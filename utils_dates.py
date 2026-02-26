from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def _parse_input_date(input_date: str | None) -> date:
    if input_date:
        return date.fromisoformat(input_date)
    return datetime.now(KST).date()


def compute_previous_week_thursday_key(input_date: str | None = None) -> str:
    """
    Return week_key as YYYY-MM-DD for the previous week's Thursday in KST basis.

    Example:
    - input_date=2026-02-25 (Wed) -> previous week Thursday = 2026-02-19
    """
    d = _parse_input_date(input_date)
    monday = d - timedelta(days=d.weekday())
    this_week_thursday = monday + timedelta(days=3)
    previous_week_thursday = this_week_thursday - timedelta(days=7)
    return previous_week_thursday.isoformat()
