import os

from werkzeug.security import generate_password_hash

from extensions import db
from models.activity_log import ActivityLog
from models.booking import Booking, Payment
from models.setting import SystemSetting
from models.ticket import Ticket
from models.user import User
from models.wishlist import WishlistItem
from services.catalog_data import DEFAULT_DISCORD_LINK
from services.catalog_sync_service import (
    apply_featured_movie_details,
    backfill_missing_movie_posters,
    sync_sample_poster_catalog,
    sync_booking_catalog_from_imdbapi,
    sync_booking_catalog_from_tmdb,
    sync_curated_upcoming_catalog,
    sync_theater_network,
)

def create_default_admin():
    admin_email = "nchethan066@gmail.com"
    admin_password = "admin123"
    old_admin_email = "nchethan066@gmai.com"

    old_admin = User.query.filter_by(email=old_admin_email).first()
    if old_admin:
        Ticket.query.filter_by(user_id=old_admin.id).delete()
        old_bookings = Booking.query.filter_by(user_id=old_admin.id).all()

        for booking in old_bookings:
            Payment.query.filter_by(booking_id=booking.id).delete()
            db.session.delete(booking)

        db.session.delete(old_admin)
        db.session.commit()

    existing_admin = User.query.filter_by(email=admin_email).first()

    if existing_admin:
        existing_admin.name = "Admin"
        existing_admin.role = "admin"
        db.session.commit()
    else:
        admin = User(
            name="Admin",
            email=admin_email,
            password=generate_password_hash(admin_password),
            role="admin"
        )

        db.session.add(admin)
        db.session.commit()


def create_default_settings():
    settings = SystemSetting.query.first()

    if not settings:
        settings = SystemSetting()
        db.session.add(settings)
        db.session.commit()
        return

    if not settings.support_discord_link:
        settings.support_discord_link = DEFAULT_DISCORD_LINK
        db.session.commit()


def ensure_schema_updates():
    with db.engine.connect() as connection:
        booking_columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(bookings)")
        }
        ticket_columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(tickets)")
        }
        setting_columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(system_settings)")
        }
        movie_columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(movies)")
        }
        user_columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(users)")
        }
        payment_columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(payments)")
        }
        theater_columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(theaters)")
        }
        screen_columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(screens)")
        }
        review_columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(reviews)")
        }

        connection.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS imdb_image_cache (
                tconst VARCHAR(20) PRIMARY KEY,
                title VARCHAR(300),
                poster_url VARCHAR(600),
                backdrop_url VARCHAR(600),
                source VARCHAR(50),
                updated_at VARCHAR(30)
            )
            """
        )

        if "booked_at" not in booking_columns:
            connection.exec_driver_sql("ALTER TABLE bookings ADD COLUMN booked_at DATETIME")

        if "cancelled_at" not in booking_columns:
            connection.exec_driver_sql("ALTER TABLE bookings ADD COLUMN cancelled_at DATETIME")

        if "external_booking_url" not in booking_columns:
            connection.exec_driver_sql("ALTER TABLE bookings ADD COLUMN external_booking_url VARCHAR(500)")

        booking_updates = {
            "refund_status": "ALTER TABLE bookings ADD COLUMN refund_status VARCHAR(50) DEFAULT ''",
            "refund_reference": "ALTER TABLE bookings ADD COLUMN refund_reference VARCHAR(120) DEFAULT ''",
        }

        for column, statement in booking_updates.items():
            if column not in booking_columns:
                connection.exec_driver_sql(statement)

        if "booking_id" not in ticket_columns:
            connection.exec_driver_sql("ALTER TABLE tickets ADD COLUMN booking_id INTEGER")

        if "trailer_url" not in movie_columns:
            connection.exec_driver_sql("ALTER TABLE movies ADD COLUMN trailer_url VARCHAR(500)")

        movie_updates = {
            "justwatch_url": "ALTER TABLE movies ADD COLUMN justwatch_url VARCHAR(500)",
            "bookmyshow_url": "ALTER TABLE movies ADD COLUMN bookmyshow_url VARCHAR(500)",
            "bookmyshow_movie_url": "ALTER TABLE movies ADD COLUMN bookmyshow_movie_url VARCHAR(500)",
            "bookmyshow_ticket_url": "ALTER TABLE movies ADD COLUMN bookmyshow_ticket_url VARCHAR(500)",
            "tmdb_id": "ALTER TABLE movies ADD COLUMN tmdb_id INTEGER",
            "tmdb_url": "ALTER TABLE movies ADD COLUMN tmdb_url VARCHAR(300)",
            "data_source": "ALTER TABLE movies ADD COLUMN data_source VARCHAR(50) DEFAULT 'manual'",
            "runtime_minutes": "ALTER TABLE movies ADD COLUMN runtime_minutes INTEGER",
            "certificate": "ALTER TABLE movies ADD COLUMN certificate VARCHAR(20)",
            "cast_names": "ALTER TABLE movies ADD COLUMN cast_names TEXT",
            "director_names": "ALTER TABLE movies ADD COLUMN director_names TEXT",
            "writer_names": "ALTER TABLE movies ADD COLUMN writer_names TEXT",
            "backdrop_url": "ALTER TABLE movies ADD COLUMN backdrop_url VARCHAR(500)",
            "interested_count": "ALTER TABLE movies ADD COLUMN interested_count INTEGER DEFAULT 0",
            "release_status": "ALTER TABLE movies ADD COLUMN release_status VARCHAR(50) DEFAULT 'Coming Soon'",
        }

        for column, statement in movie_updates.items():
            if column not in movie_columns:
                connection.exec_driver_sql(statement)

        if "profile_picture" not in user_columns:
            connection.exec_driver_sql("ALTER TABLE users ADD COLUMN profile_picture VARCHAR(255) DEFAULT ''")

        if "google_id" not in user_columns:
            connection.exec_driver_sql("ALTER TABLE users ADD COLUMN google_id VARCHAR(120)")

        user_updates = {
            "email_verified": "ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT 0",
            "email_verification_token": "ALTER TABLE users ADD COLUMN email_verification_token VARCHAR(120) DEFAULT ''",
            "password_reset_token": "ALTER TABLE users ADD COLUMN password_reset_token VARCHAR(120) DEFAULT ''",
            "password_reset_expires_at": "ALTER TABLE users ADD COLUMN password_reset_expires_at DATETIME",
            "remember_login": "ALTER TABLE users ADD COLUMN remember_login BOOLEAN DEFAULT 0",
            "subscription_plan": "ALTER TABLE users ADD COLUMN subscription_plan VARCHAR(30) DEFAULT 'free'",
            "subscription_status": "ALTER TABLE users ADD COLUMN subscription_status VARCHAR(30) DEFAULT 'active'",
            "subscription_started_at": "ALTER TABLE users ADD COLUMN subscription_started_at DATETIME",
            "subscription_expires_at": "ALTER TABLE users ADD COLUMN subscription_expires_at DATETIME",
        }

        for column, statement in user_updates.items():
            if column not in user_columns:
                connection.exec_driver_sql(statement)

        payment_updates = {
            "user_id": "ALTER TABLE payments ADD COLUMN user_id INTEGER",
            "purpose": "ALTER TABLE payments ADD COLUMN purpose VARCHAR(50) DEFAULT 'booking'",
            "provider_reference": "ALTER TABLE payments ADD COLUMN provider_reference VARCHAR(120)",
            "receipt_number": "ALTER TABLE payments ADD COLUMN receipt_number VARCHAR(80) DEFAULT ''",
            "failure_reason": "ALTER TABLE payments ADD COLUMN failure_reason VARCHAR(255) DEFAULT ''",
            "refunded_at": "ALTER TABLE payments ADD COLUMN refunded_at DATETIME",
            "created_at": "ALTER TABLE payments ADD COLUMN created_at DATETIME",
        }

        for column, statement in payment_updates.items():
            if column not in payment_columns:
                connection.exec_driver_sql(statement)

        theater_updates = {
            "amenities": "ALTER TABLE theaters ADD COLUMN amenities TEXT DEFAULT ''",
            "parking_info": "ALTER TABLE theaters ADD COLUMN parking_info VARCHAR(255) DEFAULT ''",
            "food_available": "ALTER TABLE theaters ADD COLUMN food_available BOOLEAN DEFAULT 1",
            "map_url": "ALTER TABLE theaters ADD COLUMN map_url VARCHAR(500) DEFAULT ''",
        }

        for column, statement in theater_updates.items():
            if column not in theater_columns:
                connection.exec_driver_sql(statement)

        screen_updates = {
            "vip_seats": "ALTER TABLE screens ADD COLUMN vip_seats INTEGER DEFAULT 0",
            "premium_seats": "ALTER TABLE screens ADD COLUMN premium_seats INTEGER DEFAULT 0",
            "standard_seats": "ALTER TABLE screens ADD COLUMN standard_seats INTEGER DEFAULT 0",
            "couple_seats": "ALTER TABLE screens ADD COLUMN couple_seats INTEGER DEFAULT 0",
            "wheelchair_seats": "ALTER TABLE screens ADD COLUMN wheelchair_seats INTEGER DEFAULT 0",
        }

        for column, statement in screen_updates.items():
            if column not in screen_columns:
                connection.exec_driver_sql(statement)

        review_updates = {
            "likes": "ALTER TABLE reviews ADD COLUMN likes INTEGER DEFAULT 0",
            "report_count": "ALTER TABLE reviews ADD COLUMN report_count INTEGER DEFAULT 0",
            "status": "ALTER TABLE reviews ADD COLUMN status VARCHAR(30) DEFAULT 'approved'",
        }

        for column, statement in review_updates.items():
            if column not in review_columns:
                connection.exec_driver_sql(statement)

        setting_updates = {
            "site_name": "ALTER TABLE system_settings ADD COLUMN site_name VARCHAR(100) DEFAULT 'CineVerseX'",
            "support_email": "ALTER TABLE system_settings ADD COLUMN support_email VARCHAR(120) DEFAULT 'support@cineversex.com'",
            "support_discord_link": f"ALTER TABLE system_settings ADD COLUMN support_discord_link VARCHAR(255) DEFAULT '{DEFAULT_DISCORD_LINK}'",
            "support_phone": "ALTER TABLE system_settings ADD COLUMN support_phone VARCHAR(20) DEFAULT ''",
            "booking_enabled": "ALTER TABLE system_settings ADD COLUMN booking_enabled BOOLEAN DEFAULT 1",
            "registration_enabled": "ALTER TABLE system_settings ADD COLUMN registration_enabled BOOLEAN DEFAULT 1",
            "max_seats_per_booking": "ALTER TABLE system_settings ADD COLUMN max_seats_per_booking INTEGER DEFAULT 6",
            "cancel_hours_before_show": "ALTER TABLE system_settings ADD COLUMN cancel_hours_before_show INTEGER DEFAULT 2",
            "booking_fee": "ALTER TABLE system_settings ADD COLUMN booking_fee FLOAT DEFAULT 0.0",
            "tax_percentage": "ALTER TABLE system_settings ADD COLUMN tax_percentage FLOAT DEFAULT 0.0",
            "payment_gateway_enabled": "ALTER TABLE system_settings ADD COLUMN payment_gateway_enabled BOOLEAN DEFAULT 0",
            "email_notifications_enabled": "ALTER TABLE system_settings ADD COLUMN email_notifications_enabled BOOLEAN DEFAULT 0",
            "tmdb_last_sync": "ALTER TABLE system_settings ADD COLUMN tmdb_last_sync VARCHAR(20) DEFAULT ''",
        }

        for column, statement in setting_updates.items():
            if column not in setting_columns:
                connection.exec_driver_sql(statement)

        connection.commit()


def initialize_app_data():
    db.create_all()
    ensure_schema_updates()
    create_default_settings()
    create_default_admin()
    sync_theater_network()

    if os.environ.get("ENABLE_STARTUP_CATALOG_SYNC", "").lower() in {"1", "true", "yes"}:
        if not sync_booking_catalog_from_tmdb() and not sync_booking_catalog_from_imdbapi():
            sync_curated_upcoming_catalog()

        backfill_missing_movie_posters(limit=12)
    elif not os.environ.get("SKIP_CURATED_CATALOG_SEED", "").lower() in {"1", "true", "yes"}:
        sync_curated_upcoming_catalog()

    sync_sample_poster_catalog()
    apply_featured_movie_details()
