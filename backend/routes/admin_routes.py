from flask import Blueprint, render_template, session, redirect, url_for

from models.user import User
from models.movie import Movie
from models.theater import Theater
from models.booking import Booking
from models.ticket import Ticket
from models.show import Show

admin_bp = Blueprint("admin_bp", __name__)


@admin_bp.route("/admin/dashboard")
def admin_dashboard():

    if session.get("user_role") != "admin":
        return "Access denied. Admin only."

    total_users = User.query.count()
    total_movies = Movie.query.count()
    total_theaters = Theater.query.count()
    total_bookings = Booking.query.count()

    tickets = Ticket.query.all()

    total_revenue = 0

    tickets = Ticket.query.all()

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
def manage_users():

    users = User.query.all()

    return render_template(
        "manage_users.html",
        users=users
    )