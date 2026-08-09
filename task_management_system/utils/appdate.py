from datetime import datetime, timedelta

# Africa/Nairobi (EAT) — fixed UTC+3 offset, no DST to account for.
APP_UTC_OFFSET_HOURS = 3


def app_now():
    """Current datetime in the app's configured timezone. Used wherever
    'today' must match what the user actually sees on their own clock —
    e.g. weekly-plan day-locking — rather than the server's raw UTC date,
    which flips over up to 3 hours later than local midnight and would
    make the lock boundary wrong for part of every day."""

    return datetime.utcnow() + timedelta(hours=APP_UTC_OFFSET_HOURS)


def app_today():
    return app_now().date()
