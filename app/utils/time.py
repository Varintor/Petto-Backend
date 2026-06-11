from datetime import datetime, timezone, timedelta

# All `created_at` / `updated_at` columns are DateTime(timezone=True), so any
# Python datetime used in arithmetic or filter comparisons against them must
# also be tz-aware — otherwise psycopg2/Python raise
# "can't subtract offset-naive and offset-aware datetimes".
#
# We use Asia/Bangkok (UTC+7) instead of plain UTC so day/month boundaries
# ("today", "this month", "streak") match the user's local view. Postgres
# converts between zones automatically when comparing.
BANGKOK_TZ = timezone(timedelta(hours=7))


def now_bkk() -> datetime:
    """Current time as a tz-aware datetime in Asia/Bangkok."""
    return datetime.now(BANGKOK_TZ)


def today_bkk():
    """Today's date in Bangkok local time."""
    return now_bkk().date()
