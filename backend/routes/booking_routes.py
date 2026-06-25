import os
import qrcode

from flask import (
    Blueprint,
    render_template,
    request,
    session,
    redirect,
    url_for,
    current_app
)

from extensions import db
from models.show import Show
from models.booking import Booking, Payment
from models.ticket import Ticket

booking_bp = Blueprint("booking_bp", __name__)


@booking_bp.route("/show/<int:show_id>/seats")
def seat_selection(show_id):

    if "user_id" not in session:
        return redirect(url_for("auth_bp.login"))

    show = Show.query.get_or_404(show_id)

    seats = []
    rows = ["A", "B", "C", "D", "E", "F", "G", "H"]

    for row in rows:
        for num in range(1, 11):
            seats.append(f"{row}{num}")

    bookings = Booking.query.filter_by(
        show_id=show.id,
        status="confirmed"
    ).all()

    booked_seats = []

    for booking in bookings:
        booked_seats.extend(booking.seats.split(","))

    return render_template(
        "seat_selection.html",
        show=show,
        seats=seats,
        booked_seats=booked_seats
    )


@booking_bp.route("/book/<int:show_id>", methods=["POST"])
def book_ticket(show_id):

    if "user_id" not in session:
        return redirect(url_for("auth_bp.login"))

    show = Show.query.get_or_404(show_id)

    seats = request.form["seats"]
    total_amount = float(request.form["total_amount"])

    if not seats:
        return "Please select at least one seat"

    selected_seats = seats.split(",")

    existing_bookings = Booking.query.filter_by(
        show_id=show.id,
        status="confirmed"
    ).all()

    booked_seats = []

    for booking in existing_bookings:
        booked_seats.extend(booking.seats.split(","))

    for seat in selected_seats:
        if seat in booked_seats:
            return f"Seat {seat} is already booked"

    booking = Booking(
        user_id=session["user_id"],
        show_id=show.id,
        seats=seats,
        total_amount=total_amount,
        status="confirmed"
    )

    db.session.add(booking)
    db.session.commit()

    payment = Payment(
        booking_id=booking.id,
        amount=total_amount,
        method="UPI",
        status="success"
    )

    db.session.add(payment)
    db.session.commit()

    ticket = Ticket(
        user_id=session["user_id"],
        movie_name="KGF Chapter 2",
        theatre_name="Roopa",
        show_time=show.show_time,
        seat_numbers=seats,
        total_amount=total_amount,
        status="Booked"
    )

    db.session.add(ticket)
    db.session.commit()

    qr_data = (
        f"Ticket ID: {ticket.id}\n"
        f"Movie: {ticket.movie_name}\n"
        f"Theatre: {ticket.theatre_name}\n"
        f"Show Time: {ticket.show_time}\n"
        f"Seats: {ticket.seat_numbers}\n"
        f"Amount: ₹{ticket.total_amount}"
    )

    qr_folder = os.path.join(
        current_app.root_path,
        "static",
        "qrcodes"
    )

    if not os.path.isdir(qr_folder):
       os.mkdir(qr_folder)

    qr_filename = f"ticket_{ticket.id}.png"
    qr_path = os.path.join(qr_folder, qr_filename)

    qr_img = qrcode.make(qr_data)
    qr_img.save(qr_path)

    ticket.qr_code = f"qrcodes/{qr_filename}"

    db.session.commit()

    return redirect(url_for("ticket_bp.my_tickets"))


@booking_bp.route("/bookings")
def bookings():

    if "user_id" not in session:
        return redirect(url_for("auth_bp.login"))

    user_bookings = Booking.query.filter_by(
        user_id=session["user_id"]
    ).all()

    return render_template(
        "bookings.html",
        bookings=user_bookings
    )


@booking_bp.route("/ticket/<int:booking_id>")
def ticket_details(booking_id):

    if "user_id" not in session:
        return redirect(url_for("auth_bp.login"))

    booking = Booking.query.get_or_404(booking_id)

    return render_template(
        "ticket_details.html",
        booking=booking
    )