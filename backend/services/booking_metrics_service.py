from sqlalchemy import func

from extensions import db
from models.booking import Booking, Payment
from models.movie import Movie
from models.show import Show
from models.theater import Theater
from models.ticket import Ticket
from models.user import User

CONFIRMED_BOOKING_STATUSES = ("booked", "confirmed", "paid")
CANCELLED_BOOKING_STATUSES = ("cancelled", "canceled")
EXTERNAL_BOOKING_STATUSES = ("opened bookmyshow", "external", "link opened")


def normalized_status(column):
    return func.lower(func.coalesce(column, ""))


def confirmed_booking_filter():
    return normalized_status(Booking.status).in_(CONFIRMED_BOOKING_STATUSES)


def cancelled_booking_filter():
    return normalized_status(Booking.status).in_(CANCELLED_BOOKING_STATUSES)


def external_booking_filter():
    return normalized_status(Booking.status).in_(EXTERNAL_BOOKING_STATUSES)


def active_engagement_filter():
    return ~cancelled_booking_filter()


def active_bookings_query():
    return Booking.query.filter(confirmed_booking_filter())


def cancelled_bookings_query():
    return Booking.query.filter(cancelled_booking_filter())


def external_link_opens_query():
    return Booking.query.filter(external_booking_filter())


def active_revenue_query():
    return db.session.query(func.coalesce(func.sum(Booking.total_amount), 0)).filter(
        confirmed_booking_filter()
    )


def build_admin_dashboard_metrics():
    popular_movie = (
        db.session.query(
            Movie.title,
            func.count(Booking.id).label("action_count"),
        )
        .join(Show, Show.movie_id == Movie.id)
        .join(Booking, Booking.show_id == Show.id)
        .filter(active_engagement_filter())
        .group_by(Movie.title)
        .order_by(func.count(Booking.id).desc())
        .first()
    )

    popular_theater = (
        db.session.query(
            Theater.name,
            func.count(Booking.id).label("action_count"),
        )
        .join(Show, Show.theater_id == Theater.id)
        .join(Booking, Booking.show_id == Show.id)
        .filter(active_engagement_filter())
        .group_by(Theater.name)
        .order_by(func.count(Booking.id).desc())
        .first()
    )

    return {
        "total_users": User.query.count(),
        "total_movies": Movie.query.count(),
        "total_theaters": Theater.query.count(),
        "total_bookings": active_bookings_query().count(),
        "all_booking_rows": Booking.query.count(),
        "cancelled_bookings": cancelled_bookings_query().count(),
        "external_link_opens": external_link_opens_query().count(),
        "total_revenue": round(float(active_revenue_query().scalar() or 0), 2),
        "ticket_rows": Ticket.query.count(),
        "payment_rows": Payment.query.count(),
        "popular_movie": popular_movie,
        "popular_theater": popular_theater,
    }
