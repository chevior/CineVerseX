from flask import request, session

from extensions import db
from models.activity_log import ActivityLog
from services.discord_service import send_discord_log


IMPORTANT_ACTIONS = {
    "Admin Login",
    "New User Registration",
    "Ticket Booked",
    "Ticket Cancelled",
    "Movie Added",
    "Movie Edited",
    "Movie Deleted",
    "Payment Success",
    "Payment Failure",
    "Settings Changed",
}


def log_activity(action, details="", user_id=None, notify=False):
    try:
        log = ActivityLog(
            user_id=user_id or session.get("user_id"),
            action=action,
            details=details or "",
            ip_address=request.headers.get("X-Forwarded-For", request.remote_addr or ""),
            user_agent=(request.headers.get("User-Agent") or "")[:255],
        )
        db.session.add(log)
        db.session.commit()
    except Exception as error:
        db.session.rollback()
        print("Activity log failed:", error)
        return None

    if notify or action in IMPORTANT_ACTIONS:
        send_discord_log(action, details or "Event recorded.")

    return log
