from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import func

from extensions import db
from models.booking import Booking
from models.movie import Movie
from models.show import Show
from models.theater import Screen, Theater
from models.user import User
from services.booking_metrics_service import (
    active_engagement_filter,
    cancelled_booking_filter,
    confirmed_booking_filter,
    external_booking_filter,
)


def _date_key(value):
    return value.strftime("%Y-%m-%d") if value else ""


def _month_key(value):
    return value.strftime("%Y-%m") if value else ""


def _week_key(value):
    if not value:
        return ""

    year, week, _ = value.isocalendar()
    return f"{year}-W{week:02d}"


def _seat_count(seats):
    if not seats or seats == "External":
        return 0

    return len([seat for seat in seats.split(",") if seat.strip()])


def _sum_grouped_revenue(bookings, key_fn):
    grouped = {}

    for booking in bookings:
        key = key_fn(booking.booked_at)
        if not key:
            continue

        grouped[key] = grouped.get(key, 0) + float(booking.total_amount or 0)

    return sorted(grouped.items())


def _top_rows(query, limit=10):
    return [{"label": label or "Unknown", "value": value or 0} for label, value in query.limit(limit).all()]


def build_advanced_analytics():
    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)
    active_since = now - timedelta(days=30)

    booked = Booking.query.filter(confirmed_booking_filter()).all()
    cancelled_count = Booking.query.filter(cancelled_booking_filter()).count()
    total_bookings = len(booked)
    all_booking_records = Booking.query.count()
    external_link_opens = Booking.query.filter(external_booking_filter()).count()
    total_revenue = sum(float(booking.total_amount or 0) for booking in booked)

    booked_seats = sum(_seat_count(booking.seats) for booking in booked)
    total_capacity = (
        db.session.query(func.sum(Screen.total_seats))
        .join(Show, Show.screen_id == Screen.id)
        .scalar()
        or 0
    )
    occupancy_percent = round((booked_seats / total_capacity) * 100, 1) if total_capacity else 0

    peak_hours = Counter()

    for booking in booked:
        if booking.booked_at:
            peak_hours[booking.booked_at.strftime("%I %p")] += 1

    top_peak_hours = [
        {"label": hour, "value": count}
        for hour, count in peak_hours.most_common(10)
    ]

    bookings_by_movie = db.session.query(
        Movie.title,
        func.count(Booking.id)
    ).join(Show, Show.movie_id == Movie.id)\
     .join(Booking, Booking.show_id == Show.id)\
     .filter(active_engagement_filter())\
     .group_by(Movie.title)\
     .order_by(func.count(Booking.id).desc())

    bookings_by_theater = db.session.query(
        Theater.name,
        func.count(Booking.id)
    ).join(Show, Show.theater_id == Theater.id)\
     .join(Booking, Booking.show_id == Show.id)\
     .filter(active_engagement_filter())\
     .group_by(Theater.name)\
     .order_by(func.count(Booking.id).desc())

    active_users = db.session.query(func.count(func.distinct(Booking.user_id)))\
        .filter(Booking.booked_at >= active_since)\
        .filter(active_engagement_filter())\
        .scalar() or 0

    new_users_this_month = User.query.filter(User.created_at >= month_start).count()

    return {
        "summary": {
            "total_revenue": round(total_revenue, 2),
            "total_bookings": total_bookings,
            "all_booking_records": all_booking_records,
            "cancelled_bookings": cancelled_count,
            "external_link_opens": external_link_opens,
            "occupancy_percent": occupancy_percent,
            "active_users": active_users,
            "new_users_this_month": new_users_this_month,
            "booked_seats": booked_seats,
            "total_capacity": total_capacity,
        },
        "daily_revenue": _sum_grouped_revenue(booked, _date_key),
        "weekly_revenue": _sum_grouped_revenue(booked, _week_key),
        "monthly_revenue": _sum_grouped_revenue(booked, _month_key),
        "bookings_by_movie": _top_rows(bookings_by_movie, 10),
        "bookings_by_theater": _top_rows(bookings_by_theater, 10),
        "top_movies": _top_rows(bookings_by_movie.filter(confirmed_booking_filter()), 10),
        "top_theaters": _top_rows(bookings_by_theater.filter(confirmed_booking_filter()), 10),
        "peak_hours": top_peak_hours,
    }
