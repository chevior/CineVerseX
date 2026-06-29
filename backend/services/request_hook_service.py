from datetime import datetime
import os

from flask import current_app, redirect, render_template, request, session, url_for

from models.setting import SystemSetting
from services.catalog_sync_service import (
    backfill_missing_movie_posters,
    sync_booking_catalog_from_imdbapi,
    sync_booking_catalog_from_tmdb,
)


def check_maintenance_mode():
    settings = SystemSetting.query.first()

    if not settings or not settings.maintenance_mode:
        return None

    allowed_endpoints = {
        "auth_bp.login",
        "auth_bp.logout",
        "static",
        "health"
    }

    if request.endpoint in allowed_endpoints:
        return None

    if session.get("user_role") == "admin":
        return None

    return render_template("maintenance.html"), 503


def require_login_for_member_features():
    public_endpoints = {
        "home",
        "health",
        "static",
        "generated_movie_poster",
        "auth_bp.login",
        "auth_bp.register",
        "auth_bp.logout",
        "auth_bp.reset_password",
        "movie_bp.movies",
        "movie_bp.search_movies",
        "movie_bp.movie_details",
        "movie_bp.imdb_movie_details",
        "movie_bp.imdb_poster",
        "api_bp.movies",
        "api_bp.movie_details",
        "api_bp.theaters",
        "api_bp.shows",
        "api_bp.upcoming",
        "api_bp.trending",
        "google_auth_bp.google_login",
        "google_auth_bp.google_callback",
        "payment_bp.pricing",
        "show_bp.shows",
        "theater_bp.theaters",
    }

    if request.endpoint in public_endpoints:
        return None

    if request.endpoint and request.endpoint.startswith("static"):
        return None

    if session.get("user_id"):
        return None

    return redirect(url_for("auth_bp.login"))


def refresh_booking_catalog_daily():
    if os.environ.get("ENABLE_DAILY_CATALOG_SYNC", "").lower() not in {"1", "true", "yes"}:
        return None

    if request.endpoint not in {"home", "movie_bp.movies", "show_bp.shows"}:
        return None

    today_key = datetime.utcnow().strftime("%Y-%m-%d")

    if current_app.config.get("CATALOG_SYNC_ATTEMPT_DATE") == today_key:
        return None

    current_app.config["CATALOG_SYNC_ATTEMPT_DATE"] = today_key

    if not sync_booking_catalog_from_tmdb():
        sync_booking_catalog_from_imdbapi()

    backfill_missing_movie_posters(limit=12)

    return None
