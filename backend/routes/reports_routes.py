from flask import Blueprint, render_template

from auth.guards import admin_required
from services.report_service import (
    bookings_csv_report,
    movies_csv_report,
    revenue_csv_report,
    users_csv_report,
)

reports_bp = Blueprint("reports_bp", __name__, url_prefix="/admin/reports")


@reports_bp.route("")
@admin_required
def reports():
    return render_template("reports.html")


@reports_bp.route("/bookings.csv")
@admin_required
def download_bookings_report():
    return bookings_csv_report()


@reports_bp.route("/users.csv")
@admin_required
def download_users_report():
    return users_csv_report()


@reports_bp.route("/movies.csv")
@admin_required
def download_movies_report():
    return movies_csv_report()


@reports_bp.route("/revenue.csv")
@admin_required
def download_revenue_report():
    return revenue_csv_report()
