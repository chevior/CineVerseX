from flask import Blueprint, render_template, session, redirect, url_for

from extensions import db
from models.user import User
from models.movie import Movie
from models.theater import Theater
from models.booking import Booking
from models.ticket import Ticket
from models.show import Show
from models.booking import Payment

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

    if session.get("user_role") != "admin":
        return "Access denied. Admin only."

    users = User.query.all()

    return render_template(
        "manage_users.html",
        users=users
    )


@admin_bp.route("/admin/delete-user/<int:user_id>")
def delete_user(user_id):

    if session.get("user_role") != "admin":
        return "Access denied"

    user = User.query.get_or_404(user_id)

    if user.role == "admin":
        return "Cannot delete admin"

    user_bookings = Booking.query.filter_by(user_id=user.id).all()

    for booking in user_bookings:

        payment = Payment.query.filter_by(
            booking_id=booking.id
        ).first()

        if payment:
            db.session.delete(payment)

        db.session.delete(booking)

    user_tickets = Ticket.query.filter_by(user_id=user.id).all()

    for ticket in user_tickets:
        db.session.delete(ticket)

    db.session.delete(user)

    db.session.commit()

    return redirect(url_for("admin_bp.manage_users"))