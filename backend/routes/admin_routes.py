from flask import Blueprint, flash, render_template, request, session, redirect, url_for
from sqlalchemy import func

from auth.guards import admin_required
from extensions import db
from models.user import User
from models.movie import Movie
from models.theater import Theater
from models.booking import Booking
from models.ticket import Ticket
from models.show import Show
from models.booking import Payment
from models.setting import SystemSetting

admin_bp = Blueprint("admin_bp", __name__)


def normalize_url(value):
    value = (value or "").strip()

    if value and not value.startswith(("http://", "https://")):
        return f"https://{value}"

    return value


@admin_bp.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    total_users = User.query.count()
    total_movies = Movie.query.count()
    total_theaters = Theater.query.count()
    total_bookings = Booking.query.count()

    tickets = Ticket.query.all()

    total_revenue = 0

    for ticket in tickets:
        total_revenue += ticket.total_amount

    return render_template(
        "admin_dashboard.html",
        total_users=total_users,
        total_movies=total_movies,
        total_theaters=total_theaters,
        total_bookings=total_bookings,
        total_revenue=total_revenue
    )


@admin_bp.route("/admin/users")
@admin_required
def manage_users():
    users = User.query.all()

    return render_template(
        "manage_users.html",
        users=users
    )


@admin_bp.route("/admin/delete-user/<int:user_id>")
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)

    if user.role == "admin":
        return "Cannot delete admin"

    user_bookings = Booking.query.filter_by(user_id=user.id).all()

    for booking in user_bookings:
        Payment.query.filter_by(booking_id=booking.id).delete()
        db.session.delete(booking)

    Ticket.query.filter_by(user_id=user.id).delete()

    db.session.delete(user)
    db.session.commit()

    return redirect(url_for("admin_bp.manage_users"))


@admin_bp.route("/admin/system-settings", methods=["GET", "POST"])
@admin_required
def system_settings():
    settings = SystemSetting.query.first()

    if not settings:
        settings = SystemSetting()
        db.session.add(settings)
        db.session.commit()

    if request.method == "POST":
        settings.site_name = request.form.get("site_name", "CineVerseX").strip()
        settings.support_discord_link = normalize_url(
            request.form.get("support_discord_link", "")
        )
        settings.support_phone = request.form.get("support_phone", "").strip()

        settings.maintenance_mode = "maintenance_mode" in request.form
        settings.booking_enabled = "booking_enabled" in request.form
        settings.registration_enabled = "registration_enabled" in request.form

        settings.max_seats_per_booking = max(
            1,
            int(request.form.get("max_seats_per_booking") or 6)
        )
        settings.cancel_hours_before_show = max(
            0,
            int(request.form.get("cancel_hours_before_show") or 2)
        )

        settings.booking_fee = max(
            0.0,
            float(request.form.get("booking_fee") or 0)
        )
        settings.tax_percentage = max(
            0.0,
            float(request.form.get("tax_percentage") or 0)
        )

        settings.payment_gateway_enabled = "payment_gateway_enabled" in request.form
        settings.email_notifications_enabled = "email_notifications_enabled" in request.form

        db.session.commit()
        flash("System settings updated successfully.", "success")
        return redirect(url_for("admin_bp.system_settings"))

    return render_template("system_settings.html", settings=settings)


@admin_bp.route("/revenue-charts")
@admin_required
def revenue_charts():
    daily_revenue = db.session.query(
        func.date(Booking.booked_at),
        func.sum(Booking.total_amount)
    ).filter(
        Booking.status == "Booked"
    ).group_by(
        func.date(Booking.booked_at)
    ).all()

    status_count = db.session.query(
        Booking.status,
        func.count(Booking.id)
    ).group_by(
        Booking.status
    ).all()

    popular_movies = db.session.query(
        Movie.title,
        func.count(Booking.id)
    ).join(Show, Show.movie_id == Movie.id)\
     .join(Booking, Booking.show_id == Show.id)\
     .filter(Booking.status == "Booked")\
     .group_by(Movie.title)\
     .order_by(func.count(Booking.id).desc())\
     .limit(5).all()

    return render_template(
        "revenue_charts.html",
        daily_revenue=daily_revenue,
        status_count=status_count,
        popular_movies=popular_movies
    )
