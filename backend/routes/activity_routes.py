from flask import Blueprint, render_template

from auth.guards import admin_required
from models.activity_log import ActivityLog

activity_bp = Blueprint("activity_bp", __name__, url_prefix="/admin/activity")


@activity_bp.route("")
@admin_required
def activity_logs():
    logs = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(300).all()
    return render_template("activity_logs.html", logs=logs)
