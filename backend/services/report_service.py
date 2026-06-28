import csv
from io import StringIO

from flask import Response
from sqlalchemy import func

from extensions import db
from models.booking import Booking, Payment
from models.movie import Movie
from models.show import Show
from models.theater import Theater
from models.user import User
from services.booking_metrics_service import confirmed_booking_filter
from services.catalog_data import BOOKMYSHOW_HOME_URL


def format_datetime(value):
    if not value:
        return ""

    return value.strftime("%Y-%m-%d %H:%M:%S")


def csv_response(filename, headers, rows):
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


def bookings_csv_report():
    rows = (
        db.session.query(Booking, User, Show, Movie, Theater, Payment)
        .outerjoin(User, Booking.user_id == User.id)
        .outerjoin(Show, Booking.show_id == Show.id)
        .outerjoin(Movie, Show.movie_id == Movie.id)
        .outerjoin(Theater, Show.theater_id == Theater.id)
        .outerjoin(Payment, Payment.booking_id == Booking.id)
        .order_by(Booking.booked_at.desc(), Booking.id.desc())
        .all()
    )

    return csv_response(
        "cineversex-bookings-report.csv",
        [
            "Booking ID",
            "User Name",
            "User Email",
            "Movie",
            "Theater",
            "Screen ID",
            "Seats",
            "Amount",
            "Booking Status",
            "Payment Method",
            "Payment Status",
            "External Booking URL",
            "Booked At",
            "Cancelled At",
        ],
        [
            [
                booking.id,
                user.name if user else "",
                user.email if user else "",
                movie.title if movie else "",
                theater.name if theater else "",
                show.screen_id if show else "",
                booking.seats or "",
                booking.total_amount or 0,
                booking.status or "",
                payment.method if payment else "",
                payment.status if payment else "",
                booking.external_booking_url or "",
                format_datetime(booking.booked_at),
                format_datetime(booking.cancelled_at),
            ]
            for booking, user, show, movie, theater, payment in rows
        ],
    )


def users_csv_report():
    users = User.query.order_by(User.created_at.desc(), User.id.desc()).all()

    return csv_response(
        "cineversex-users-report.csv",
        ["User ID", "Name", "Email", "Role", "Created At"],
        [
            [
                user.id,
                user.name,
                user.email,
                user.role,
                format_datetime(user.created_at),
            ]
            for user in users
        ],
    )


def movies_csv_report():
    movies = Movie.query.order_by(Movie.created_at.desc(), Movie.title.asc()).all()

    return csv_response(
        "cineversex-movies-report.csv",
        [
            "Movie ID",
            "Title",
            "Language",
            "Genre",
            "Release Date",
            "Rating",
            "Runtime Minutes",
            "Certificate",
            "Data Source",
            "Poster URL",
            "Trailer URL",
            "JustWatch URL",
            "BookMyShow URL",
            "Created At",
        ],
        [
            [
                movie.id,
                movie.title,
                movie.language or "",
                movie.genre or "",
                movie.release_date or "",
                movie.rating or 0,
                movie.runtime_minutes or "",
                movie.certificate or "",
                movie.data_source or "",
                movie.poster_url or "",
                movie.trailer_url or "",
                movie.justwatch_url or "",
                BOOKMYSHOW_HOME_URL,
                format_datetime(movie.created_at),
            ]
            for movie in movies
        ],
    )


def revenue_csv_report():
    daily_rows = (
        db.session.query(
            func.date(Booking.booked_at).label("report_date"),
            func.count(Booking.id).label("booking_count"),
            func.sum(Booking.total_amount).label("revenue"),
        )
        .filter(confirmed_booking_filter())
        .group_by(func.date(Booking.booked_at))
        .order_by(func.date(Booking.booked_at).desc())
        .all()
    )

    return csv_response(
        "cineversex-revenue-report.csv",
        ["Date", "Booked Tickets", "Revenue"],
        [
            [
                report_date,
                booking_count or 0,
                round(revenue or 0, 2),
            ]
            for report_date, booking_count, revenue in daily_rows
        ],
    )
