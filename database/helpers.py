"""Small shared helpers for the database package."""
from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_today() -> str:
    """Today's UTC date as an ISO string (the format used in the database)."""
    return utc_now().date().isoformat()


def not_registered_message(userid: int) -> str:
    return (
        f"Sorry <@{userid}> you're not registered yet, "
        "send a message in general chat to register yourself."
    )
