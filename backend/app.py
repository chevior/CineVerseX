import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, Response, render_template
from flask_login import LoginManager
from dotenv import load_dotenv

load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from config import Config
from extensions import db, mail

from models.user import User
from models.movie import Movie
from models.setting import SystemSetting

from routes.auth_routes import auth_bp
from routes.movie_routes import movie_bp
from routes.theater_routes import theater_bp
from routes.booking_routes import booking_bp
from routes.admin_routes import admin_bp
from routes.show_routes import show_bp
from routes.ticket_routes import ticket_bp
from routes.activity_routes import activity_bp
from routes.api_routes import api_bp
from routes.google_auth_routes import google_auth_bp
from routes.payment_routes import payment_bp
from routes.profile_routes import profile_bp
from routes.reports_routes import reports_bp
from routes.wishlist_routes import wishlist_bp

from services.display_service import neutral_public_copy
from services.catalog_data import BOOKMYSHOW_HOME_URL
from services.catalog_sync_service import bookmyshow_search_url
from services.home_service import build_home_context, generated_movie_poster_svg
from services.request_hook_service import (
    check_maintenance_mode as check_maintenance_mode_service,
    refresh_booking_catalog_daily as refresh_booking_catalog_daily_service,
    require_login_for_member_features as require_login_for_member_features_service,
)
from services.startup_service import (
    initialize_app_data,
)
from services.security_service import (
    apply_security_headers,
    check_rate_limit,
    configure_security,
    ensure_csrf_token,
    validate_csrf_request,
)



app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static"
)

app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY
app.config["MAIL_SERVER"] = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
app.config["MAIL_PORT"] = int(os.environ.get("MAIL_PORT", 587))
app.config["MAIL_USE_TLS"] = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME", "")
app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD", "")
app.config["MAIL_DEFAULT_SENDER"] = os.environ.get(
    "MAIL_DEFAULT_SENDER",
    app.config["MAIL_USERNAME"]
)
configure_security(app)

db.init_app(app)
mail.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth_bp.login"


app.jinja_env.filters["neutral_copy"] = neutral_public_copy


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
app.register_blueprint(activity_bp)
app.register_blueprint(api_bp)
app.register_blueprint(google_auth_bp)
app.register_blueprint(payment_bp)
app.register_blueprint(profile_bp)
app.register_blueprint(reports_bp)
app.register_blueprint(wishlist_bp)


@app.route("/")
def home():
    return render_template("home.html", **build_home_context())


@app.route("/health")
def health():
    return "CineVerseX Flask is running", 200


@app.route("/generated-poster/<int:movie_id>.svg")
def generated_movie_poster(movie_id):
    movie = db.session.get(Movie, movie_id)

    if not movie:
        return Response("", status=404)

    return Response(generated_movie_poster_svg(movie), mimetype="image/svg+xml")


@app.context_processor
def inject_system_settings():
    today = datetime.utcnow()

    def effective_bookmyshow_movie_url(movie):
        title = getattr(movie, "title", "") or getattr(movie, "primaryTitle", "")
        direct_url = bookmyshow_search_url(title)

        if direct_url != BOOKMYSHOW_HOME_URL:
            return direct_url

        for attribute_name in ("bookmyshow_url", "bookmyshow_movie_url", "bookmyshow_ticket_url"):
            candidate = (getattr(movie, attribute_name, "") or "").strip()

            if candidate and candidate != BOOKMYSHOW_HOME_URL:
                return candidate

        return BOOKMYSHOW_HOME_URL

    return {
        "system_settings": SystemSetting.query.first(),
        "csrf_token": ensure_csrf_token,
        "today_key": today.strftime("%Y-%m-%d"),
        "current_year": today.year,
        "bookmyshow_url_for_title": bookmyshow_search_url,
        "bookmyshow_movie_url": effective_bookmyshow_movie_url,
    }




@app.before_request
def check_maintenance_mode():
    return check_maintenance_mode_service()


@app.before_request
def rate_limit_requests():
    return check_rate_limit()


@app.before_request
def protect_post_requests():
    return validate_csrf_request()


@app.before_request
def require_login_for_member_features():
    return require_login_for_member_features_service()


@app.before_request
def refresh_booking_catalog_daily():
    return refresh_booking_catalog_daily_service()


@app.after_request
def set_security_headers(response):
    return apply_security_headers(response)


with app.app_context():
    initialize_app_data()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
