import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, render_template
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


with app.app_context():
    db.create_all()
    create_default_admin()


if __name__ == "__main__":
    app.run(debug=True)
