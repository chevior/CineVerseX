import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, render_template, request, session
from flask_login import LoginManager
from werkzeug.security import generate_password_hash

from config import Config
from extensions import db

from models.user import User
from models.movie import Movie
from models.theater import Theater, Screen
from models.show import Show
from models.booking import Booking, Payment
from models.setting import SystemSetting
from models.ticket import Ticket

from routes.auth_routes import auth_bp
from routes.movie_routes import movie_bp
from routes.theater_routes import theater_bp
from routes.booking_routes import booking_bp
from routes.admin_routes import admin_bp
from routes.show_routes import show_bp
from routes.ticket_routes import ticket_bp


DEFAULT_DISCORD_LINK = "https://discord.gg/rFrDA6veF"


app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static"
)

app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth_bp.login"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


app.register_blueprint(auth_bp)
app.register_blueprint(movie_bp)
app.register_blueprint(theater_bp)
app.register_blueprint(booking_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(show_bp)
app.register_blueprint(ticket_bp)


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/health")
def health():
    return "CineVerseX Flask is running", 200


@app.context_processor
def inject_system_settings():
    return {
        "system_settings": SystemSetting.query.first()
    }


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

        if "booked_at" not in booking_columns:
            connection.exec_driver_sql("ALTER TABLE bookings ADD COLUMN booked_at DATETIME")

        if "cancelled_at" not in booking_columns:
            connection.exec_driver_sql("ALTER TABLE bookings ADD COLUMN cancelled_at DATETIME")

        if "booking_id" not in ticket_columns:
            connection.exec_driver_sql("ALTER TABLE tickets ADD COLUMN booking_id INTEGER")

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
        }

        for column, statement in setting_updates.items():
            if column not in setting_columns:
                connection.exec_driver_sql(statement)

        connection.commit()


@app.before_request
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


with app.app_context():
    db.create_all()
    ensure_schema_updates()
    create_default_settings()
    create_default_admin()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
