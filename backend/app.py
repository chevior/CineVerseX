import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, render_template
from flask_login import LoginManager

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


app = Flask(__name__, template_folder="templates", static_folder="static")
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth_bp.login"


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


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
    return "CineVerseX Flask is running"


# Only create tables locally, not on Vercel
if os.environ.get("VERCEL") != "1":
    with app.app_context():
        db.create_all()


if __name__ == "__main__":
    app.run(debug=True)