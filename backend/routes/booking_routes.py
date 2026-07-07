import os
import qrcode
from datetime import datetime
from uuid import uuid4

from flask import (
    Blueprint,
    flash,
    render_template,
    request,
    session,
    redirect,
    url_for,
    current_app
)

from extensions import db
from auth.guards import login_required
from models.show import Show
from models.booking import Booking, Payment
from models.setting import SystemSetting
from models.ticket import Ticket
from models.user import User
from services.activity_service import log_activity
from services.catalog_data import BOOKMYSHOW_HOME_URL
from services.catalog_sync_service import bookmyshow_search_url
from services.email_service import send_ticket_email

booking_bp = Blueprint("booking_bp", __name__)

ACTIVE_BOOKING_STATUSES = ("Booked", "confirmed")


def get_settings():
    settings = SystemSetting.query.first()

    if not settings:
        settings = SystemSetting()
        db.session.add(settings)
        db.session.commit()

    return settings


def parse_show_time(show_time):
    if not show_time:
        return None

    formats = (
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M",
        "%d-%m-%Y %H:%M",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%d %I:%M %p",
        "%d-%m-%Y %I:%M %p",
        "%I:%M %p",
    )

    for date_format in formats:
        try:
            return datetime.strptime(show_time, date_format)
        except ValueError:
            continue

    return None


def effective_bookmyshow_url(movie):
    if not movie:
        return BOOKMYSHOW_HOME_URL

    return movie.bookmyshow_url or bookmyshow_search_url(movie.title)


def seat_label(prefix, count):
    return [f"{prefix}{number}" for number in range(1, max(count, 0) + 1)]


def screen_seats(screen):
    total = screen.total_seats if screen else 80
    vip = screen.vip_seats or max(total // 10, 4)
    premium = screen.premium_seats or max(total // 4, 12)
    couple = screen.couple_seats or max(total // 20, 2)
    wheelchair = screen.wheelchair_seats or 2
    standard = screen.standard_seats or max(total - vip - premium - couple - wheelchair, 0)

    return {
        "VIP": seat_label("V", vip),
        "Premium": seat_label("P", premium),
        "Standard": seat_label("S", standard),
        "Couple": seat_label("C", couple),
        "Wheelchair": seat_label("W", wheelchair),
    }


def seat_price(base_price, seat):
    base = float(base_price or 0)
    multipliers = {
        "V": 1.8,
        "P": 1.35,
        "C": 2.0,
        "W": 1.0,
        "S": 1.0,
    }
    return round(base * multipliers.get(seat[:1], 1.0), 2)


@booking_bp.route("/show/<int:show_id>/seats")
def seat_selection(show_id):
    show = Show.query.get_or_404(show_id)
    settings = get_settings()
    grouped_seats = screen_seats(show.screen)
    seats = [seat for group in grouped_seats.values() for seat in group]
    booked_seats = []

    for booking in Booking.query.filter(
        Booking.show_id == show.id,
        Booking.status.in_(ACTIVE_BOOKING_STATUSES)
    ).all():
        booked_seats.extend((booking.seats or "").split(","))

    return render_template(
        "seat_selection.html",
        show=show,
        settings=settings,
        grouped_seats=grouped_seats,
        seats=seats,
        booked_seats=booked_seats,
        seat_prices={seat: seat_price(show.price, seat) for seat in seats},
        bookmyshow_url=effective_bookmyshow_url(show.movie),
    )


@booking_bp.route("/book/<int:show_id>", methods=["POST"])
@login_required
def book_ticket(show_id):
    settings = get_settings()

    if not settings.booking_enabled:
        flash("Bookings are currently disabled by admin.", "warning")
        return redirect(url_for("movie_bp.movies"))

    show = Show.query.get_or_404(show_id)
    movie_name = show.movie.title if show.movie else "Unknown Movie"
    theatre_name = show.theater.name if show.theater else "Unknown Theatre"

    seats = request.form["seats"]

    if not seats:
        return "Please select at least one seat"

    selected_seats = seats.split(",")
    selected_seats = [seat for seat in selected_seats if seat]

    if len(selected_seats) > settings.max_seats_per_booking:
        flash(
            f"Maximum {settings.max_seats_per_booking} seats allowed per booking.",
            "danger"
        )
        return redirect(url_for("booking_bp.seat_selection", show_id=show.id))

    subtotal = sum(seat_price(show.price, seat) for seat in selected_seats)
    tax_amount = subtotal * (settings.tax_percentage or 0) / 100
    expected_total = subtotal + float(settings.booking_fee or 0) + tax_amount
    total_amount = round(expected_total, 2)

    existing_bookings = Booking.query.filter(
        Booking.show_id == show.id,
        Booking.status.in_(ACTIVE_BOOKING_STATUSES)
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
        status="Booked"
    )

    db.session.add(booking)
    db.session.commit()
    log_activity("Payment Success", f"Payment recorded for booking #{booking.id}.", notify=True)

    payment = Payment(
        booking_id=booking.id,
        user_id=session["user_id"],
        amount=total_amount,
        method=request.form.get("payment_method", "UPI"),
        status="success",
        receipt_number=f"CX-{datetime.utcnow().strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}",
        provider_reference=f"pay_{uuid4().hex[:14]}"
    )

    db.session.add(payment)
    db.session.commit()

    ticket = Ticket(
        user_id=session["user_id"],
        booking_id=booking.id,
        movie_name=movie_name,
        theatre_name=theatre_name,
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
        f"Amount: Rs. {ticket.total_amount}"
    )

    qr_folder = os.path.join(
        current_app.root_path,
        "static",
        "qrcodes"
    )

    os.makedirs(qr_folder, exist_ok=True)

    qr_filename = f"ticket_{ticket.id}.png"
    qr_path = os.path.join(qr_folder, qr_filename)

    qr_img = qrcode.make(qr_data)
    qr_img.save(qr_path)

    ticket.qr_code = f"qrcodes/{qr_filename}"

    db.session.commit()

    user = db.session.get(User, session["user_id"])
    if user:
        send_ticket_email(user, booking, ticket)
    log_activity("Ticket Booked", f"Booking #{booking.id} for {movie_name}, seats {seats}.", notify=True)

    return redirect(url_for("ticket_bp.my_tickets"))


@booking_bp.route("/cancel-ticket/<int:booking_id>", methods=["POST"])
@login_required
def cancel_ticket(booking_id):
    settings = get_settings()
    booking = Booking.query.get_or_404(booking_id)

    if booking.user_id != session["user_id"] and session.get("user_role") != "admin":
        flash("You are not allowed to cancel this ticket.", "danger")
        return redirect(url_for("ticket_bp.my_tickets"))

    if booking.status == "Cancelled":
        flash("Ticket is already cancelled.", "warning")
        return redirect(url_for("ticket_bp.my_tickets"))

    show_time = parse_show_time(booking.show.show_time if booking.show else None)
    if show_time:
        hours_until_show = (show_time - datetime.utcnow()).total_seconds() / 3600

        if hours_until_show < settings.cancel_hours_before_show:
            flash(
                f"Tickets can only be cancelled at least {settings.cancel_hours_before_show} hours before show time.",
                "danger"
            )
            return redirect(url_for("ticket_bp.my_tickets"))

    booking.status = "Cancelled"
    booking.refund_status = "Pending" if float(booking.total_amount or 0) > 0 else "Not Required"
    booking.refund_reference = f"refund_{uuid4().hex[:12]}" if booking.refund_status == "Pending" else ""
    booking.cancelled_at = datetime.utcnow()

    ticket = Ticket.query.filter_by(booking_id=booking.id).first()
    if ticket:
        ticket.status = "Cancelled"

    payment = Payment.query.filter_by(booking_id=booking.id).first()
    if payment and payment.status == "success":
        payment.status = "refunded"
        payment.refunded_at = datetime.utcnow()

    db.session.commit()
    log_activity("Ticket Cancelled", f"Booking #{booking.id} cancelled.", notify=True)

    flash("Ticket cancelled successfully. Refund status has been updated.", "success")
    return redirect(url_for("ticket_bp.my_tickets"))


@booking_bp.route("/bookings")
@login_required
def bookings():
    user_bookings = Booking.query.filter_by(
        user_id=session["user_id"]
    ).all()

    return render_template(
        "bookings.html",
        bookings=user_bookings
    )


@booking_bp.route("/ticket/<int:booking_id>")
@login_required
def ticket_details(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    if booking.user_id != session["user_id"] and session.get("user_role") != "admin":
        return "Access denied", 403

    return render_template(
        "ticket_details.html",
        booking=booking
    )


@booking_bp.route("/booking-history")
@login_required
def booking_history():
    if session.get("user_role") == "admin":
        bookings = Booking.query.order_by(Booking.booked_at.desc()).all()
    else:
        bookings = Booking.query.filter_by(user_id=session["user_id"])\
            .order_by(Booking.booked_at.desc()).all()

    return render_template("booking_history.html", bookings=bookings)
