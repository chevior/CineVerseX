import os
import sqlite3
import sys
import html
import json
from datetime import datetime, timedelta
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, Response, render_template, request, session
from flask_login import LoginManager
from sqlalchemy import func
from werkzeug.security import generate_password_hash

from config import Config
from extensions import db, mail

from models.user import User
from models.movie import Movie
from models.theater import Theater, Screen
from models.show import Show
from models.booking import Booking, Payment
from models.setting import SystemSetting
from models.ticket import Ticket
from models.review import Review

from routes.auth_routes import auth_bp
from routes.movie_routes import movie_bp
from routes.theater_routes import theater_bp
from routes.booking_routes import booking_bp
from routes.admin_routes import admin_bp
from routes.show_routes import show_bp
from routes.ticket_routes import ticket_bp


DEFAULT_DISCORD_LINK = "https://discord.gg/rFrDA6veF"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
IMDBAPI_BASE_URL = "https://api.imdbapi.dev"
BOOKMYSHOW_HOME_URL = "https://in.bookmyshow.com/"
KNOWN_BOOKMYSHOW_LINKS = {
    "the super mario galaxy movie": {
        "movie": "https://in.bookmyshow.com/movies/the-super-mario-galaxy-movie/ET00465655",
        "ticket": "",
    },
    "spider-man: brand new day": {
        "movie": "https://in.bookmyshow.com/movies/spiderman-brand-new-day/ET00447840",
        "ticket": "",
    },
    "avengers: doomsday": {
        "movie": "https://in.bookmyshow.com/movies/avengers-doomsday/ET00439706",
        "ticket": "",
    },
    "the odyssey": {
        "movie": "https://in.bookmyshow.com/movies/the-odyssey/ET00452034",
        "ticket": "https://in.bookmyshow.com/movies/bengaluru/the-odyssey/buytickets/ET00452034/",
    },
    "balan: the boy": {
        "movie": "https://in.bookmyshow.com/movies/bengaluru/balan-the-boy/ET00502388",
        "ticket": "https://in.bookmyshow.com/movies/bengaluru/balan-the-boy/buytickets/ET00502388/",
    },
    "carry on jatta 4": {
        "movie": "https://in.bookmyshow.com/movies/bengaluru/carry-on-jatta-4/ET00374796",
        "ticket": "",
    },
    "jindagi once more": {
        "movie": "https://in.bookmyshow.com/movies/bengaluru/jindagi-once-more/ET00501011",
        "ticket": "",
    },
    "welcome to the jungle": {
        "movie": "https://in.bookmyshow.com/movies/bengaluru/welcome-to-the-jungle/ET00369379",
        "ticket": "",
    },
    "tumbadchi manjula": {
        "movie": "https://in.bookmyshow.com/movies/bengaluru/tumbadchi-manjula/ET00496931",
        "ticket": "https://in.bookmyshow.com/movies/bengaluru/tumbadchi-manjula/buytickets/ET00496931/20260607",
    },
    "toxic: a fairy tale for grown-ups": {
        "movie": "https://in.bookmyshow.com/movies/toxic-a-fairy-tale-for-grown-ups/ET00378770",
        "ticket": "",
    },
    "ranabaali": {
        "movie": "https://in.bookmyshow.com/movies/bengaluru/ranabaali/ET00483565",
        "ticket": "",
    },
    "drishyam 3": {
        "movie": "https://in.bookmyshow.com/movies/bengaluru/drishyam-3/ET00487295",
        "ticket": "https://in.bookmyshow.com/movies/bengaluru/drishyam-3/buytickets/ET00487295/",
    },
    "rakkayie": {
        "movie": "https://in.bookmyshow.com/movies/bengaluru/rakkayie/ET00420342",
        "ticket": "",
    },
    "send help": {
        "movie": "https://in.bookmyshow.com/movies/bengaluru/send-help/ET00481597",
        "ticket": "https://in.bookmyshow.com/movies/bengaluru/send-help/buytickets/ET00483802/",
    },
    "project hail mary": {
        "movie": "https://in.bookmyshow.com/movies/bengaluru/project-hail-mary/ET00451760",
        "ticket": "https://in.bookmyshow.com/movies/bengaluru/project-hail-mary-bengaluru/buytickets/et00451760",
    },
    "michael": {
        "movie": "https://in.bookmyshow.com/movies/bengaluru/michael/ET00470110",
        "ticket": "https://in.bookmyshow.com/movies/bengaluru/michael-bengaluru/buytickets/et00470110",
    },
}
CURATED_UPCOMING_RELEASES = [
    {
        "title": "The Super Mario Galaxy Movie",
        "description": "Mario, Luigi, Peach, and friends return for a new animated adventure inspired by the Super Mario Galaxy games.",
        "language": "English, Hindi, Tamil, Telugu",
        "genre": "Adventure,Animation,Comedy,Family,Fantasy",
        "release_date": "2026-04-03",
        "rating": 0,
    },
    {
        "title": "Minions & Monsters",
        "description": "The Minions return for a new Illumination theatrical adventure packed with chaotic comedy, family-friendly mayhem, and monster-sized trouble.",
        "language": "English, Hindi, Tamil, Telugu",
        "genre": "Animation,Comedy,Family",
        "release_date": "2026-07-01",
        "rating": 0,
    },
    {
        "title": "Varanasi",
        "description": "A Telugu-led pan-Indian adventure drama scheduled for a wide multi-language theatrical rollout.",
        "language": "Telugu, Hindi, Tamil, Kannada, Malayalam",
        "genre": "Action,Adventure,Drama",
        "release_date": "2026-07-03",
        "rating": 0,
    },
    {
        "title": "The Paradise",
        "description": "A large-scale Telugu action drama listed among upcoming theatrical releases across Indian languages.",
        "language": "Telugu, Hindi, Tamil, Kannada, Malayalam",
        "genre": "Action,Drama",
        "release_date": "2026-07-09",
        "rating": 0,
    },
    {
        "title": "Balan: The Boy",
        "description": "A multi-language Indian drama arriving for family audiences across Malayalam, Kannada, Hindi, Tamil, and Telugu.",
        "language": "Malayalam, Kannada, Hindi, Tamil, Telugu",
        "genre": "Drama,Family",
        "release_date": "2026-07-10",
        "rating": 0,
    },
    {
        "title": "The Odyssey",
        "description": "Christopher Nolan's mythic epic brings Homer's legendary voyage to the big screen with large-scale adventure and spectacle.",
        "language": "English, Hindi, Tamil, Telugu",
        "genre": "Adventure,Drama,Fantasy",
        "release_date": "2026-07-17",
        "rating": 0,
    },
    {
        "title": "Carry on Jatta 4",
        "description": "The Punjabi comedy franchise returns with another round of family confusion, romance, and high-energy comic chaos.",
        "language": "Punjabi",
        "genre": "Comedy,Drama",
        "release_date": "2026-07-24",
        "rating": 0,
    },
    {
        "title": "Spider-Man: Brand New Day",
        "description": "Peter Parker begins a fresh chapter as Spider-Man, facing new pressure, new threats, and a dangerous evolution in his powers.",
        "language": "English, Hindi, Tamil, Telugu",
        "genre": "Action,Adventure,Superhero",
        "release_date": "2026-07-31",
        "rating": 0,
    },
    {
        "title": "Toy Story 5",
        "description": "Pixar's toys return for another animated theatrical adventure about friendship, change, and a new generation of play.",
        "language": "English, Hindi, Tamil, Telugu",
        "genre": "Adventure,Animation,Comedy,Family",
        "release_date": "2026-08-07",
        "rating": 0,
    },
    {
        "title": "Supergirl",
        "description": "Kara Zor-El steps into a new DC cinematic adventure with cosmic action, identity, and superhero stakes.",
        "language": "English, Hindi, Tamil, Telugu",
        "genre": "Action,Adventure,Sci-Fi,Superhero",
        "release_date": "2026-08-14",
        "rating": 0,
    },
    {
        "title": "Jindagi Once More",
        "description": "A Gujarati theatrical release centered on second chances, relationships, and rediscovering joy.",
        "language": "Gujarati",
        "genre": "Drama,Family",
        "release_date": "2026-08-07",
        "rating": 0,
    },
    {
        "title": "Welcome To The Jungle",
        "description": "A Hindi ensemble comedy-adventure built around chaos, action, and a large comic cast.",
        "language": "Hindi",
        "genre": "Comedy,Adventure",
        "release_date": "2026-08-14",
        "rating": 0,
    },
    {
        "title": "Tumbadchi Manjula",
        "description": "A Marathi theatrical release bringing regional drama and mystery to upcoming cinema listings.",
        "language": "Marathi",
        "genre": "Drama,Mystery",
        "release_date": "2026-08-21",
        "rating": 0,
    },
    {
        "title": "Toxic: A Fairy Tale for Grown-ups",
        "description": "A pan-Indian action drama led by Kannada cinema and planned for multiple Indian languages.",
        "language": "Kannada, Hindi, Tamil, Telugu, Malayalam",
        "genre": "Action,Drama",
        "release_date": "2026-08-28",
        "rating": 0,
    },
    {
        "title": "Evil Dead Burn",
        "description": "The Evil Dead franchise returns with a new horror chapter built for theatrical scares and genre fans.",
        "language": "English, Hindi, Tamil, Telugu",
        "genre": "Horror,Thriller",
        "release_date": "2026-09-04",
        "rating": 0,
    },
    {
        "title": "Cocktail 2",
        "description": "A Hindi romantic drama continuation aimed at multiplex audiences with music, relationships, and urban emotion.",
        "language": "Hindi",
        "genre": "Drama,Romance",
        "release_date": "2026-09-04",
        "rating": 0,
    },
    {
        "title": "Ranabaali",
        "description": "A Telugu-led multi-language release planned for South Indian and Hindi audiences.",
        "language": "Telugu, Tamil, Kannada, Malayalam, Hindi",
        "genre": "Action,Drama",
        "release_date": "2026-09-11",
        "rating": 0,
    },
    {
        "title": "Colony",
        "description": "A Korean-language theatrical listing for viewers looking beyond Indian and Hollywood releases.",
        "language": "Korean",
        "genre": "Drama,Thriller",
        "release_date": "2026-09-18",
        "rating": 0,
    },
    {
        "title": "Drishyam 3",
        "description": "The Hindi mystery-thriller franchise returns with another chapter of secrets, investigation, and family stakes.",
        "language": "Hindi",
        "genre": "Drama,Mystery,Thriller",
        "release_date": "2026-10-02",
        "rating": 0,
    },
    {
        "title": "Peddi",
        "description": "A Telugu sports-action drama scheduled as a major Indian theatrical release.",
        "language": "Telugu, Hindi, Tamil, Kannada, Malayalam",
        "genre": "Action,Drama,Sports",
        "release_date": "2026-10-09",
        "rating": 0,
    },
    {
        "title": "Maa Inti Bangaaram",
        "description": "A Telugu family drama planned for theatrical audiences looking for emotion, relationships, and regional storytelling.",
        "language": "Telugu",
        "genre": "Drama,Family",
        "release_date": "2026-10-16",
        "rating": 0,
    },
    {
        "title": "Michael",
        "description": "A musical biographical drama following Michael Jackson's rise, artistry, and cultural impact.",
        "language": "English, Hindi",
        "genre": "Biography,Drama,Music",
        "release_date": "2026-10-03",
        "rating": 0,
    },
    {
        "title": "Avengers: Doomsday",
        "description": "Marvel heroes face the rising threat of Doctor Doom in the next major Avengers event from Marvel Studios.",
        "language": "English, Hindi, Tamil, Telugu",
        "genre": "Action,Adventure,Superhero",
        "release_date": "2026-12-18",
        "rating": 0,
    },
    {
        "title": "Dune: Part Three",
        "description": "The next chapter of Denis Villeneuve's Dune saga continues the desert epic with prophecy, politics, and interstellar war.",
        "language": "English, Hindi, Tamil, Telugu",
        "genre": "Adventure,Drama,Sci-Fi",
        "release_date": "2026-12-18",
        "rating": 0,
    },
    {
        "title": "Send Help",
        "description": "A survival thriller about danger, isolation, and desperate choices after a journey goes wrong.",
        "language": "English",
        "genre": "Adventure,Horror,Thriller",
        "release_date": "2026-12-25",
        "rating": 0,
    },
    {
        "title": "Athimanoharam",
        "description": "A Malayalam family drama planned around the festive season with a warm, relationship-driven story.",
        "language": "Malayalam",
        "genre": "Drama,Family",
        "release_date": "2026-12-24",
        "rating": 0,
    },
    {
        "title": "Rakkayie",
        "description": "A Tamil-led multi-language release planned for year-end audiences across South Indian languages.",
        "language": "Tamil, Telugu, Kannada, Malayalam, Hindi",
        "genre": "Action,Drama",
        "release_date": "2026-12-31",
        "rating": 0,
    },
    {
        "title": "Shrek 5",
        "description": "Shrek, Fiona, Donkey, and the next generation of Far Far Away return for a new DreamWorks animated adventure.",
        "language": "English, Hindi",
        "genre": "Animation,Adventure,Comedy",
        "release_date": "2027-06-30",
        "rating": 0,
    },
]
FEATURED_MOVIE_DETAILS = {
    "Project Hail Mary": {
        "description": "A lone astronaut wakes up aboard a spacecraft with no memory of his mission and realizes he may be humanity's last chance. Based on Andy Weir's bestselling novel, the film follows Ryland Grace as he pieces together a desperate interstellar mission, an impossible scientific mystery, and an unexpected first-contact friendship.",
        "language": "English, Hindi, Tamil, Telugu",
        "genre": "Adventure,Drama,Sci-Fi",
        "release_date": "2026-03-20",
        "rating": 8.2,
        "justwatch_url": "https://www.justwatch.com/in/search?q=Project%20Hail%20Mary",
    }
}
THEATER_NETWORK = [
    ("PVR: Orion Mall", "Bengaluru Urban", "Orion Mall, Brigade Gateway, Dr Rajkumar Road, Rajajinagar, Bengaluru", 11, 156),
    ("PVR: Phoenix Marketcity", "Bengaluru Urban", "Phoenix Marketcity, Whitefield Main Road, Mahadevapura, Bengaluru", 9, 172),
    ("PVR: Forum South Bengaluru", "Bengaluru Urban", "Forum South Mall, Kanakapura Road, Konanakunte, Bengaluru", 12, 148),
    ("PVR: Nexus Koramangala", "Bengaluru Urban", "Nexus Mall, Hosur Road, Koramangala, Bengaluru", 8, 168),
    ("INOX: Megaplex Mall of Asia", "Bengaluru Urban", "Byatarayanapura, Yelahanka Taluk, Bellary Road, Bengaluru", 12, 188),
    ("PVR: Vega City", "Bengaluru Urban", "Vega City Mall, Bannerghatta Main Road, Bengaluru", 7, 164),
    ("INOX: Garuda Mall", "Bengaluru Urban", "Garuda Mall, Magrath Road, Ashok Nagar, Bengaluru", 5, 142),
    ("PVR: Mantri Square", "Bengaluru Urban", "Mantri Square Mall, Sampige Road, Malleshwaram, Bengaluru", 6, 150),
    ("PVR: VR Bengaluru", "Bengaluru Urban", "VR Bengaluru, Whitefield Road, Mahadevapura, Bengaluru", 9, 180),
    ("GT World Cinemas", "Bengaluru Urban", "GT World Mall, Magadi Main Road, Bengaluru", 3, 132),
    ("PVR: Elements Mall", "Bengaluru Urban", "Elements Mall, Thanisandra Main Road, Nagavara, Bengaluru", 5, 146),
    ("Gopalan Cinemas: Arcade Mall", "Bengaluru Urban", "Gopalan Arcade Mall, Mysore Road, Bengaluru", 4, 138),
    ("PVR: Lulu Mall Bengaluru", "Bengaluru Urban", "Lulu Global Mall, Mysore Road, Rajajinagar, Bengaluru", 6, 190),
    ("INOX: Megaplex Mall of Asia", "Bengaluru Urban", "Byatarayanapura, Yelahanka Taluk, Bellary Road, Bengaluru", 12, 168),
    ("PVR: Orion Mall, Dr Rajkumar Road", "Bengaluru Urban", "Orion Mall, Brigade Gateway, Dr Rajkumar Road, Malleshwaram West, Bengaluru", 11, 158),
    ("Cinepolis: Nexus Shantiniketan", "Bengaluru Urban", "Nexus Shantiniketan Mall, ITPL Main Road, Whitefield, Bengaluru", 7, 146),
    ("PVR: Superplex Forum South", "Bengaluru Urban", "Forum South Mall, Kanakapura Road, Konanakunte, Bengaluru", 12, 154),
    ("PVR: Phoenix Marketcity", "Bengaluru Urban", "Phoenix Marketcity, Whitefield Main Road, Mahadevapura, Bengaluru", 9, 160),
    ("PVR: Nexus Koramangala", "Bengaluru Urban", "Nexus Mall, Koramangala, Bengaluru", 8, 150),
    ("PVR: Vega City", "Bengaluru Urban", "Vega City Mall, Bannerghatta Main Road, Bengaluru", 7, 148),
    ("INOX: Garuda Mall", "Bengaluru Urban", "Garuda Mall, Magrath Road, Ashok Nagar, Bengaluru", 5, 142),
    ("PVR: Vaishnavi Sapphire", "Bengaluru Urban", "Vaishnavi Sapphire Mall, Yeshwanthpur, Bengaluru", 6, 150),
    ("Cinepolis: Royal Meenakshi Mall", "Bengaluru Urban", "Royal Meenakshi Mall, Bannerghatta Road, Bengaluru", 6, 144),
    ("PVR: Soul Spirit Centro Mall", "Bengaluru Urban", "Bellandur, Bengaluru", 5, 138),
    ("PVR: MSR Elements Mall", "Bengaluru Urban", "Elements Mall, Thanisandra Main Road, Nagavara, Bengaluru", 5, 142),
    ("Gopalan Cinemas: Signature Mall", "Bengaluru Urban", "Old Madras Road, Bengaluru", 4, 132),
    ("Gopalan Cinemas: Grand Mall", "Bengaluru Urban", "Old Madras Road, Bengaluru", 4, 130),
    ("PVR: Aura Park Square", "Bengaluru Urban", "Park Square Mall, ITPL, Whitefield, Bengaluru", 5, 142),
    ("PVR: Bhartiya Mall of Bengaluru", "Bengaluru Urban", "Bhartiya City, Thanisandra Main Road, Bengaluru", 7, 150),
    ("INOX: Brookefield Mall", "Bengaluru Urban", "Brookefield Mall, Kundalahalli, Bengaluru", 4, 138),
    ("INOX: Central JP Nagar", "Bengaluru Urban", "Central Mall, JP Nagar, Bengaluru", 4, 136),
    ("Cinepolis: ETA Namma Mall", "Bengaluru Urban", "ETA Namma Mall, Binny Pete, Bengaluru", 5, 142),
    ("Cinepolis: Binnypet Mall", "Bengaluru Urban", "Binnypet, Bengaluru", 5, 140),
    ("Mukunda Theatre", "Bengaluru Urban", "Maruthi Sevanagar, Bengaluru", 1, 360),
    ("Urvashi Cinema", "Bengaluru Urban", "Lalbagh Road, Bengaluru", 1, 420),
    ("Rex Theatre", "Bengaluru Urban", "Brigade Road, Bengaluru", 1, 360),
    ("Balaji Theatre", "Bengaluru Urban", "Tavarekere, Bengaluru", 1, 340),
    ("Sri Krishna Digital 4K Cinema", "Bengaluru Urban", "KR Puram, Bengaluru", 1, 330),
    ("Vaibhav Theatre", "Bengaluru Urban", "Sanjay Nagar, Bengaluru", 1, 350),
    ("Navrang Theatre", "Bengaluru Urban", "Rajajinagar, Bengaluru", 1, 380),
    ("Veeresh Cinemas", "Bengaluru Urban", "Magadi Road, Bengaluru", 2, 300),
    ("Sri Sangameshwara Chitramandira", "Vijayapura (Bengaluru Rural)", "Vijayapura, Bengaluru Rural, Karnataka", 1, 420),
    ("Sri Gowrishankar Theatre", "Vijayapura (Bengaluru Rural)", "Vijayapura, Bengaluru Rural, Karnataka", 1, 380),
    ("Sri Vinayaka Cinemas", "Nelamangala (Bengaluru Rural)", "Nelamangala, Bengaluru Rural, Karnataka", 2, 260),
    ("Venkateshwara Theatre", "Devanahalli (Bengaluru Rural)", "Devanahalli, Bengaluru Rural, Karnataka", 1, 340),
    ("Sri Krishna Theatre", "Doddaballapur (Bengaluru Rural)", "Doddaballapur, Bengaluru Rural, Karnataka", 1, 360),
    ("Raghavendra Theatre", "Hoskote (Bengaluru Rural)", "Hoskote, Bengaluru Rural, Karnataka", 1, 320),
    ("Vijay Theatre", "Anekal (Bengaluru Urban/Rural)", "Anekal, Bengaluru region, Karnataka", 1, 300),
    ("Nandi Theatre", "Devanahalli (Bengaluru Rural)", "Devanahalli, Bengaluru Rural, Karnataka", 1, 320),
    ("Sri Lakshmi Theatre", "Nelamangala (Bengaluru Rural)", "Nelamangala, Bengaluru Rural, Karnataka", 1, 310),
    ("Sri Venkateshwara Chitra Mandira", "Doddaballapur (Bengaluru Rural)", "Doddaballapur, Bengaluru Rural, Karnataka", 1, 330),
    ("Sri Balaji Talkies", "Hoskote (Bengaluru Rural)", "Hoskote, Bengaluru Rural, Karnataka", 1, 300),
    ("Anjan Theatre", "Anekal (Bengaluru Urban/Rural)", "Anekal, Bengaluru region, Karnataka", 1, 300),
]

THEATER_RENAMES = {
    "CineVerse Orion Mall": ("PVR: Orion Mall", "Bengaluru Urban", "Orion Mall, Brigade Gateway, Dr Rajkumar Road, Rajajinagar, Bengaluru"),
    "CineVerse Phoenix Marketcity": ("PVR: Phoenix Marketcity", "Bengaluru Urban", "Phoenix Marketcity, Whitefield Main Road, Mahadevapura, Bengaluru"),
    "CineVerse Forum South": ("PVR: Forum South Bengaluru", "Bengaluru Urban", "Forum South Mall, Kanakapura Road, Konanakunte, Bengaluru"),
    "CineVerse Nexus Koramangala": ("PVR: Nexus Koramangala", "Bengaluru Urban", "Nexus Mall, Hosur Road, Koramangala, Bengaluru"),
    "CineVerse Mall of Asia": ("INOX: Megaplex Mall of Asia", "Bengaluru Urban", "Byatarayanapura, Yelahanka Taluk, Bellary Road, Bengaluru"),
    "CineVerse Vega City": ("PVR: Vega City", "Bengaluru Urban", "Vega City Mall, Bannerghatta Main Road, Bengaluru"),
    "CineVerse Garuda Mall": ("INOX: Garuda Mall", "Bengaluru Urban", "Garuda Mall, Magrath Road, Ashok Nagar, Bengaluru"),
    "CineVerse Mantri Square": ("PVR: Mantri Square", "Bengaluru Urban", "Mantri Square Mall, Sampige Road, Malleshwaram, Bengaluru"),
    "CineVerse VR Bengaluru": ("PVR: VR Bengaluru", "Bengaluru Urban", "VR Bengaluru, Whitefield Road, Mahadevapura, Bengaluru"),
    "CineVerse GT World Mall": ("GT World Cinemas", "Bengaluru Urban", "GT World Mall, Magadi Main Road, Bengaluru"),
    "CineVerse Elements Mall": ("PVR: Elements Mall", "Bengaluru Urban", "Elements Mall, Thanisandra Main Road, Nagavara, Bengaluru"),
    "CineVerse Gopalan Arcade": ("Gopalan Cinemas: Arcade Mall", "Bengaluru Urban", "Gopalan Arcade Mall, Mysore Road, Bengaluru"),
    "CineVerse Lulu Global Mall": ("PVR: Lulu Mall Bengaluru", "Bengaluru Urban", "Lulu Global Mall, Mysore Road, Rajajinagar, Bengaluru"),
}


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

db.init_app(app)
mail.init_app(app)

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
    trending_movie = db.session.query(
        Movie,
        func.count(Booking.id).label("booking_count")
    ).join(Show, Show.movie_id == Movie.id)\
     .join(Booking, Booking.show_id == Show.id)\
     .filter(Booking.status == "Booked")\
     .group_by(Movie.id)\
     .order_by(func.count(Booking.id).desc())\
     .first()

    if not trending_movie:
        fallback_movie = Movie.query.order_by(Movie.rating.desc()).first()
        if fallback_movie:
            trending_movie = (fallback_movie, 0)

    today_key = datetime.utcnow().strftime("%Y-%m-%d")
    poster_first = Movie.poster_url.isnot(None).desc(), (Movie.poster_url != "").desc()
    homepage_movies = Movie.query.filter(
        Movie.data_source.in_(("tmdb", "imdbapi", "curated")),
        Movie.poster_url.isnot(None),
        Movie.poster_url != ""
    )
    hero_movies = homepage_movies.order_by(
        *poster_first,
        Movie.rating.desc(),
        Movie.title.asc()
    ).limit(5).all()
    featured_movies = homepage_movies.filter(
        Movie.release_date >= today_key
    ).order_by(
        *poster_first,
        Movie.release_date.asc(),
        Movie.rating.desc()
    ).limit(10).all()
    stream_movies = homepage_movies.order_by(
        *poster_first,
        Movie.rating.desc(),
        Movie.title.asc()
    ).offset(10).limit(10).all()
    top_rated_movies = homepage_movies.order_by(
        *poster_first,
        Movie.rating.desc(),
        Movie.title.asc()
    ).limit(10).all()

    movie_count = Movie.query.filter(
        Movie.data_source.in_(("tmdb", "imdbapi", "curated"))
    ).count()
    theater_count = Theater.query.filter(Theater.name != "BookMyShow").count()
    release_count = Show.query.join(Movie).filter(
        Movie.data_source.in_(("tmdb", "imdbapi", "curated")),
        Show.show_time >= today_key
    ).count()

    return render_template(
        "home.html",
        trending_movie=trending_movie,
        hero_movies=hero_movies,
        featured_movies=featured_movies,
        stream_movies=stream_movies,
        top_rated_movies=top_rated_movies,
        movie_count=movie_count,
        theater_count=theater_count,
        release_count=release_count
    )


@app.route("/health")
def health():
    return "CineVerseX Flask is running", 200


@app.route("/generated-poster/<int:movie_id>.svg")
def generated_movie_poster(movie_id):
    movie = db.session.get(Movie, movie_id)

    if not movie:
        return Response("", status=404)

    title = html.escape(movie.title or "CineVerse X")
    genre = html.escape((movie.genre or "Upcoming Release").replace(",", " / "))
    release = html.escape(movie.release_date or "Coming Soon")
    language = html.escape(movie.language or "All Languages")
    initial = html.escape((movie.title or "C")[:1].upper())

    palette = [
        ("#101820", "#f2aa4c", "#29a19c"),
        ("#171321", "#ff4f79", "#6ee7b7"),
        ("#111827", "#facc15", "#38bdf8"),
        ("#1a120b", "#eab308", "#ef4444"),
        ("#0f172a", "#a78bfa", "#fb7185"),
        ("#132a13", "#fef08a", "#22c55e"),
    ]
    bg, accent, secondary = palette[movie_id % len(palette)]

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="640" height="960" viewBox="0 0 640 960">
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{bg}"/>
    <stop offset="1" stop-color="#050505"/>
  </linearGradient>
  <radialGradient id="glow" cx="35%" cy="20%" r="70%">
    <stop offset="0" stop-color="{accent}" stop-opacity="0.55"/>
    <stop offset="1" stop-color="{accent}" stop-opacity="0"/>
  </radialGradient>
</defs>
<rect width="640" height="960" fill="url(#bg)"/>
<rect width="640" height="960" fill="url(#glow)"/>
<circle cx="520" cy="170" r="170" fill="{secondary}" opacity="0.16"/>
<circle cx="105" cy="785" r="190" fill="{accent}" opacity="0.14"/>
<path d="M70 122 C190 68 335 70 485 122" fill="none" stroke="{accent}" stroke-width="4" opacity="0.8"/>
<text x="72" y="155" fill="{accent}" font-family="Arial, Helvetica, sans-serif" font-size="28" font-weight="700" letter-spacing="3">CINEVERSE X</text>
<text x="320" y="422" text-anchor="middle" fill="#ffffff" font-family="Arial, Helvetica, sans-serif" font-size="176" font-weight="900" opacity="0.22">{initial}</text>
<foreignObject x="62" y="490" width="516" height="210">
  <div xmlns="http://www.w3.org/1999/xhtml" style="font-family:Arial, Helvetica, sans-serif;color:#fff;font-size:48px;font-weight:900;line-height:1.04;text-transform:uppercase;word-break:break-word;">{title}</div>
</foreignObject>
<text x="64" y="735" fill="{accent}" font-family="Arial, Helvetica, sans-serif" font-size="26" font-weight="700">{release}</text>
<foreignObject x="64" y="765" width="512" height="70">
  <div xmlns="http://www.w3.org/1999/xhtml" style="font-family:Arial, Helvetica, sans-serif;color:#e5e7eb;font-size:24px;line-height:1.25;">{genre}</div>
</foreignObject>
<text x="64" y="872" fill="#ffffff" font-family="Arial, Helvetica, sans-serif" font-size="22" opacity="0.78">{language}</text>
<rect x="64" y="896" width="512" height="2" fill="{accent}" opacity="0.65"/>
</svg>"""

    return Response(svg, mimetype="image/svg+xml")


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


def booking_catalog_imdb_path():
    configured_path = app.config.get("IMDB_DB_PATH", "").strip()

    if configured_path:
        return os.path.abspath(configured_path)

    deploy_disk_path = os.path.abspath("/var/data/cineversex.db")

    if os.path.isfile(deploy_disk_path):
        return deploy_disk_path

    return os.path.abspath(os.path.join(app.root_path, "..", "cineversex.db"))


def bookmyshow_search_url(title, city="bengaluru"):
    return BOOKMYSHOW_HOME_URL


def normalize_bookmyshow_movie_url(url):
    url = (url or "").strip()

    if not url:
        return ""

    marker = "in.bookmyshow.com/movies/"

    if marker not in url:
        return url

    prefix, path = url.split(marker, 1)
    parts = [part for part in path.split("/") if part]

    if not parts:
        return url

    if "buytickets" in parts:
        buytickets_index = parts.index("buytickets")
        if buytickets_index >= 1 and buytickets_index + 1 < len(parts):
            slug = parts[buytickets_index - 1]
            event_id = parts[buytickets_index + 1]
            return f"{prefix}{marker}{slug}/{event_id}"

    if len(parts) >= 3 and parts[2].upper().startswith("ET"):
        return f"{prefix}{marker}{parts[1]}/{parts[2]}"

    return url


def bookmyshow_links_for_title(title):
    title_key = (title or "").strip().casefold()
    known_links = KNOWN_BOOKMYSHOW_LINKS.get(title_key)

    if known_links:
        movie_url = normalize_bookmyshow_movie_url(known_links["movie"])
        return {
            "movie": movie_url,
            "ticket": "",
            "primary": movie_url,
        }

    return {
        "movie": "",
        "ticket": "",
        "primary": "",
    }


def tmdb_headers():
    bearer_token = os.environ.get("TMDB_BEARER_TOKEN", "").strip()

    if bearer_token:
        return {"Authorization": f"Bearer {bearer_token}"}

    return {}


def tmdb_url(path, params=None):
    params = params or {}
    api_key = os.environ.get("TMDB_API_KEY", "").strip()

    if api_key and not os.environ.get("TMDB_BEARER_TOKEN", "").strip():
        params["api_key"] = api_key

    return f"{TMDB_BASE_URL}{path}?{urlencode(params)}"


def tmdb_is_configured():
    return bool(
        os.environ.get("TMDB_BEARER_TOKEN", "").strip()
        or os.environ.get("TMDB_API_KEY", "").strip()
    )


def fetch_tmdb_json(path, params=None):
    request = Request(
        tmdb_url(path, params),
        headers=tmdb_headers()
    )

    with urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8"))


def imdbapi_url(path, params=None):
    query = f"?{urlencode(params or {}, doseq=True)}" if params else ""
    return f"{IMDBAPI_BASE_URL}{path}{query}"


def fetch_imdbapi_json(path, params=None, timeout=12):
    request = Request(
        imdbapi_url(path, params),
        headers={
            "accept": "application/json",
            "User-Agent": "CineVerseX/1.0 (+https://cineversex.onrender.com)",
        }
    )

    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def precision_date_to_iso(value):
    if not value:
        return ""

    year = value.get("year")
    month = value.get("month")
    day = value.get("day")

    if year and month and day:
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"

    if year and month:
        return f"{int(year):04d}-{int(month):02d}-01"

    if year:
        return f"{int(year):04d}-12-31"

    return ""


def fetch_imdbapi_release_date(title_id):
    if not title_id:
        return ""

    try:
        response = fetch_imdbapi_json(f"/titles/{title_id}/releaseDates", timeout=8)
    except Exception:
        return ""

    release_dates = response.get("releaseDates", [])

    for preferred_code in ("IN", "US", "GB"):
        for item in release_dates:
            country = item.get("country") or {}

            if country.get("code") == preferred_code:
                return precision_date_to_iso(item.get("releaseDate"))

    for item in release_dates:
        release_date = precision_date_to_iso(item.get("releaseDate"))

        if release_date:
            return release_date

    return ""


def normalize_imdbapi_title(item, fetch_release_date=False):
    title = item.get("primaryTitle") or item.get("originalTitle")

    if not title:
        return None

    title_id = item.get("id") or ""
    genres = ", ".join(item.get("genres") or [])
    languages = ", ".join(
        language.get("name", "")
        for language in item.get("spokenLanguages", [])
        if language.get("name")
    )
    rating = item.get("rating") or {}
    poster = item.get("primaryImage") or {}
    year = item.get("startYear")
    runtime_seconds = item.get("runtimeSeconds") or 0
    cast_names = ", ".join(
        person.get("displayName", "")
        for person in item.get("stars", [])[:8]
        if person.get("displayName")
    )
    director_names = ", ".join(
        person.get("displayName", "")
        for person in item.get("directors", [])[:4]
        if person.get("displayName")
    )
    writer_names = ", ".join(
        person.get("displayName", "")
        for person in item.get("writers", [])[:4]
        if person.get("displayName")
    )
    release_date = (fetch_imdbapi_release_date(title_id) if fetch_release_date else "") or (
        f"{int(year):04d}-12-31" if year else ""
    )

    return {
        "imdb_id": title_id,
        "title": title,
        "description": item.get("plot") or "IMDbAPI synced release details will update as official metadata becomes available.",
        "poster_url": poster.get("url") or "",
        "language": languages or "English, Hindi, Tamil, Telugu",
        "genre": genres or "Drama",
        "release_date": release_date,
        "rating": round(float(rating.get("aggregateRating") or 0), 1),
        "runtime_minutes": int(runtime_seconds // 60) if runtime_seconds else None,
        "certificate": "UA",
        "cast_names": cast_names,
        "director_names": director_names,
        "writer_names": writer_names,
        "backdrop_url": poster.get("url") or "",
    }


def fetch_booking_catalog_from_imdbapi(limit=120, max_pages=4):
    current_year = datetime.utcnow().year

    movies = []
    seen_titles = set()
    page_token = ""

    for _ in range(max_pages):
        params = {
            "types": ["MOVIE"],
            "startYear": current_year,
            "endYear": current_year + 2,
            "sortBy": "SORT_BY_RELEASE_DATE",
            "sortOrder": "ASC",
            "minVoteCount": 0,
        }

        if page_token:
            params["pageToken"] = page_token

        try:
            response = fetch_imdbapi_json("/titles", params)
        except Exception as error:
            print("IMDbAPI sync failed:", error)
            break

        for item in response.get("titles", []):
            normalized = normalize_imdbapi_title(item)

            if not normalized or not normalized["poster_url"]:
                continue

            title_key = (
                normalized["title"].strip().casefold(),
                normalized["release_date"][:4],
            )

            if title_key in seen_titles:
                continue

            seen_titles.add(title_key)
            movies.append(normalized)

            if len(movies) >= limit:
                return movies

        page_token = response.get("nextPageToken") or ""

        if not page_token:
            break

    return movies


def fetch_booking_catalog_from_tmdb(region="IN", pages=2):
    if not tmdb_is_configured():
        return []

    genre_response = fetch_tmdb_json(
        "/genre/movie/list",
        {"language": "en-US"}
    )
    genre_map = {
        genre["id"]: genre["name"]
        for genre in genre_response.get("genres", [])
    }

    movies = []
    seen_tmdb_ids = set()

    for endpoint in ("/movie/now_playing", "/movie/upcoming"):
        for page in range(1, pages + 1):
            response = fetch_tmdb_json(
                endpoint,
                {
                    "language": "en-US",
                    "region": region,
                    "page": page,
                }
            )

            for item in response.get("results", []):
                tmdb_id = item.get("id")

                if not tmdb_id or tmdb_id in seen_tmdb_ids:
                    continue

                seen_tmdb_ids.add(tmdb_id)
                title = item.get("title") or item.get("name")

                if not title:
                    continue

                genres = ", ".join(
                    genre_map.get(genre_id, "")
                    for genre_id in item.get("genre_ids", [])
                    if genre_map.get(genre_id)
                )

                poster_path = item.get("poster_path")
                movies.append({
                    "tmdb_id": tmdb_id,
                    "title": title,
                    "description": item.get("overview") or "No synopsis available yet.",
                    "poster_url": f"{TMDB_IMAGE_BASE_URL}{poster_path}" if poster_path else "",
                    "backdrop_url": f"{TMDB_IMAGE_BASE_URL}{item.get('backdrop_path')}" if item.get("backdrop_path") else "",
                    "language": (item.get("original_language") or "en").upper(),
                    "genre": genres or "Drama",
                    "release_date": item.get("release_date") or "",
                    "rating": round(float(item.get("vote_average") or 0), 1),
                })

    return movies


def fetch_booking_catalog_from_imdb(limit=10):
    imdb_path = booking_catalog_imdb_path()

    if not os.path.isfile(imdb_path):
        return []

    conn = sqlite3.connect(f"file:{imdb_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT
            t.primaryTitle,
            t.startYear,
            t.genres,
            r.averageRating,
            r.numVotes
        FROM imdb_titles t
        LEFT JOIN imdb_ratings r ON t.tconst = r.tconst
        WHERE t.titleType = 'movie'
        AND t.isAdult = 0
        AND t.startYear >= 2026
        GROUP BY t.primaryTitle, t.startYear
        ORDER BY
            COALESCE(r.numVotes, 0) DESC,
            COALESCE(r.averageRating, 0) DESC
        LIMIT ?
        """,
        (limit,)
    ).fetchall()
    conn.close()

    return rows


def ensure_screen(theater, screen_name, total_seats):
    screen = Screen.query.filter_by(
        theater_id=theater.id,
        screen_name=screen_name
    ).first()

    if not screen:
        screen = Screen(
            theater_id=theater.id,
            screen_name=screen_name,
            total_seats=total_seats
        )
        db.session.add(screen)
    else:
        screen.total_seats = total_seats

    return screen


def fetch_tmdb_image_match(title, release_date=""):
    if not tmdb_is_configured() or not title:
        return None

    year = (release_date or "")[:4]
    params = {
        "query": title,
        "include_adult": "false",
        "language": "en-IN",
    }

    if year.isdigit():
        params["primary_release_year"] = year

    response = fetch_tmdb_json("/search/movie", params)
    results = response.get("results", [])

    if not results and year.isdigit():
        params.pop("primary_release_year", None)
        response = fetch_tmdb_json("/search/movie", params)
        results = response.get("results", [])

    best = next((item for item in results if item.get("poster_path")), None)

    if not best:
        return None

    return {
        "tmdb_id": best.get("id"),
        "poster_url": f"{TMDB_IMAGE_BASE_URL}{best['poster_path']}",
        "backdrop_url": (
            f"{TMDB_IMAGE_BASE_URL}{best['backdrop_path']}"
            if best.get("backdrop_path")
            else ""
        ),
    }


def backfill_missing_movie_posters(limit=80):
    if not tmdb_is_configured():
        return False

    movies = (
        Movie.query
        .filter(Movie.data_source.in_(("curated", "manual")))
        .filter((Movie.poster_url.is_(None)) | (Movie.poster_url == ""))
        .order_by(Movie.release_date.asc(), Movie.title.asc())
        .limit(limit)
        .all()
    )

    updated = 0

    for movie in movies:
        try:
            match = fetch_tmdb_image_match(movie.title, movie.release_date)
        except Exception as error:
            print(f"TMDb poster lookup failed for {movie.title}:", error)
            continue

        if not match:
            continue

        movie.poster_url = match["poster_url"]
        movie.backdrop_url = match["backdrop_url"] or match["poster_url"]

        if match.get("tmdb_id") and not movie.tmdb_id:
            movie.tmdb_id = match["tmdb_id"]
            movie.tmdb_url = f"https://www.themoviedb.org/movie/{match['tmdb_id']}"

        db.session.commit()
        updated += 1

    return bool(updated)


def sync_theater_network():
    for old_name, (new_name, new_city, new_address) in THEATER_RENAMES.items():
        old_theater = Theater.query.filter_by(name=old_name).first()

        if not old_theater:
            continue

        duplicate = Theater.query.filter_by(name=new_name, city=new_city).first()

        if duplicate and duplicate.id != old_theater.id:
            for screen in old_theater.screens:
                screen.theater_id = duplicate.id

            for show in old_theater.shows:
                show.theater_id = duplicate.id

            db.session.delete(old_theater)
        else:
            old_theater.name = new_name
            old_theater.city = new_city
            old_theater.address = new_address

    db.session.flush()

    for name, city, address, total_screens, base_seats in THEATER_NETWORK:
        theater = Theater.query.filter_by(name=name, city=city).first()

        if not theater:
            theater = Theater(
                name=name,
                city=city,
                address=address,
                total_screens=total_screens
            )
            db.session.add(theater)
            db.session.flush()
        else:
            theater.address = address
            theater.total_screens = total_screens

        for index in range(1, total_screens + 1):
            screen_label = (
                f"IMAX Screen {index}"
                if index == 1 and total_screens >= 5
                else f"Screen {index}"
            )
            ensure_screen(theater, screen_label, base_seats + (index * 12))

    db.session.commit()


def sync_booking_catalog_from_imdb():
    imdb_rows = fetch_booking_catalog_from_imdb()

    if not imdb_rows:
        return

    theater_seed = THEATER_NETWORK[:8]

    theaters = []

    for name, city, address, total_screens, *_ in theater_seed:
        theater = Theater.query.filter_by(name=name, city=city).first()

        if not theater:
            theater = Theater(
                name=name,
                city=city,
                address=address,
                total_screens=total_screens
            )
            db.session.add(theater)
            db.session.flush()
        else:
            theater.address = address
            theater.total_screens = total_screens

        for index in range(1, total_screens + 1):
            ensure_screen(theater, f"Screen {index}", 96 + (index * 18))

        theaters.append(theater)

    db.session.flush()

    movies = []

    for row in imdb_rows:
        title = row["primaryTitle"]
        year = str(int(row["startYear"])) if row["startYear"] else "2026"
        genres = row["genres"] or "Drama"
        rating = float(row["averageRating"] or 0)

        movie = Movie.query.filter_by(title=title).first()

        if not movie:
            movie = Movie(
                title=title,
                description="Freshly synced from the IMDb dataset for CineVerse booking availability.",
                language="English",
                genre=genres,
                release_date=year,
                rating=rating,
                poster_url=""
            )
            db.session.add(movie)
        else:
            movie.genre = genres
            movie.release_date = year
            movie.rating = rating

        encoded_title = quote_plus(title)
        bookmyshow_links = bookmyshow_links_for_title(title)
        movie.bookmyshow_movie_url = bookmyshow_links["movie"]
        movie.bookmyshow_ticket_url = bookmyshow_links["ticket"]
        movie.bookmyshow_url = bookmyshow_links["primary"]
        movie.justwatch_url = f"https://www.justwatch.com/in/search?q={encoded_title}"
        movies.append(movie)

    db.session.flush()

    base_day = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    show_times = ("10:30", "13:45", "17:15", "20:45")
    prices = (180, 220, 260, 320)

    for movie_index, movie in enumerate(movies):
        for slot_index in range(2):
            theater = theaters[(movie_index + slot_index) % len(theaters)]
            screens = Screen.query.filter_by(theater_id=theater.id).order_by(Screen.id.asc()).all()
            screen = screens[slot_index % len(screens)]
            day = base_day + timedelta(days=movie_index % 5)
            show_time = f"{day.date()} {show_times[(movie_index + slot_index) % len(show_times)]}"

            existing_show = Show.query.filter_by(
                movie_id=movie.id,
                theater_id=theater.id,
                screen_id=screen.id,
                show_time=show_time
            ).first()

            if existing_show:
                existing_show.price = prices[(movie_index + slot_index) % len(prices)]
                continue

            db.session.add(
                Show(
                    movie_id=movie.id,
                    theater_id=theater.id,
                    screen_id=screen.id,
                    show_time=show_time,
                    price=prices[(movie_index + slot_index) % len(prices)]
                )
            )

    db.session.commit()


def sync_curated_upcoming_catalog():
    theater = Theater.query.filter_by(name="BookMyShow", city="Bengaluru").first()

    if not theater:
        theater = Theater(
            name="BookMyShow",
            city="Bengaluru",
            address="External booking partner",
            total_screens=1
        )
        db.session.add(theater)
        db.session.flush()

    screen = ensure_screen(theater, "External Booking", 0)
    db.session.flush()

    show_time = "10:00"

    for item in CURATED_UPCOMING_RELEASES:
        movie = Movie.query.filter_by(title=item["title"]).first()

        if not movie:
            movie = Movie(
                title=item["title"],
                description=item["description"]
            )
            db.session.add(movie)

        movie.description = item["description"]
        movie.poster_url = ""
        movie.backdrop_url = movie.backdrop_url or ""
        movie.language = item["language"]
        movie.genre = item["genre"]
        movie.release_date = item["release_date"]
        movie.rating = item["rating"]
        movie.certificate = movie.certificate or "UA"
        movie.data_source = "curated"

        bookmyshow_links = bookmyshow_links_for_title(item["title"])
        movie.bookmyshow_movie_url = bookmyshow_links["movie"]
        movie.bookmyshow_ticket_url = bookmyshow_links["ticket"]
        movie.bookmyshow_url = bookmyshow_links["primary"]
        movie.justwatch_url = f"https://www.justwatch.com/in/search?q={quote_plus(item['title'])}"

        db.session.flush()

        existing_show = Show.query.filter_by(
            movie_id=movie.id,
            theater_id=theater.id,
            screen_id=screen.id
        ).first()

        if existing_show:
            existing_show.show_time = f"{item['release_date']} {show_time}"
            existing_show.price = 0
            continue

        db.session.add(
            Show(
                movie_id=movie.id,
                theater_id=theater.id,
                screen_id=screen.id,
                show_time=f"{item['release_date']} {show_time}",
                price=0
            )
        )

    db.session.commit()


def sync_booking_catalog_from_imdbapi():
    imdbapi_movies = fetch_booking_catalog_from_imdbapi()

    if not imdbapi_movies:
        return False

    theater = Theater.query.filter_by(name="BookMyShow", city="Bengaluru").first()

    if not theater:
        theater = Theater(
            name="BookMyShow",
            city="Bengaluru",
            address="External booking partner",
            total_screens=1
        )
        db.session.add(theater)
        db.session.flush()

    screen = ensure_screen(theater, "External Booking", 0)
    db.session.flush()

    for item in imdbapi_movies:
        movie = Movie.query.filter_by(title=item["title"]).first()

        if not movie:
            movie = Movie(
                title=item["title"],
                description=item["description"]
            )
            db.session.add(movie)

        movie.description = item["description"]
        movie.poster_url = item["poster_url"]
        movie.backdrop_url = item["backdrop_url"] or item["poster_url"]
        movie.language = item["language"]
        movie.genre = item["genre"]
        movie.release_date = item["release_date"]
        movie.rating = item["rating"]
        movie.runtime_minutes = item["runtime_minutes"]
        movie.certificate = item["certificate"]
        movie.cast_names = item["cast_names"]
        movie.director_names = item["director_names"]
        movie.writer_names = item["writer_names"]
        movie.tmdb_url = f"https://www.imdb.com/title/{item['imdb_id']}/" if item["imdb_id"] else ""
        movie.data_source = "imdbapi"

        bookmyshow_links = bookmyshow_links_for_title(item["title"])
        movie.bookmyshow_movie_url = bookmyshow_links["movie"]
        movie.bookmyshow_ticket_url = bookmyshow_links["ticket"]
        movie.bookmyshow_url = bookmyshow_links["primary"]
        movie.justwatch_url = f"https://www.justwatch.com/in/search?q={quote_plus(item['title'])}"

        db.session.flush()

        existing_show = Show.query.filter_by(
            movie_id=movie.id,
            theater_id=theater.id,
            screen_id=screen.id
        ).first()

        show_time = f"{item['release_date'] or str(datetime.utcnow().year) + '-12-31'} 10:00"

        if existing_show:
            existing_show.show_time = show_time
            existing_show.price = 0
            continue

        db.session.add(
            Show(
                movie_id=movie.id,
                theater_id=theater.id,
                screen_id=screen.id,
                show_time=show_time,
                price=0
            )
        )

    db.session.commit()
    return True


def apply_featured_movie_details():
    for title, details in FEATURED_MOVIE_DETAILS.items():
        movie = Movie.query.filter_by(title=title).first()

        if not movie:
            continue

        movie.description = details["description"]
        movie.language = details["language"]
        movie.genre = details["genre"]
        movie.release_date = details["release_date"]
        movie.rating = details["rating"]
        movie.runtime_minutes = movie.runtime_minutes or details.get("runtime_minutes")
        movie.certificate = movie.certificate or details.get("certificate", "UA")
        movie.cast_names = movie.cast_names or details.get("cast_names", "")
        movie.director_names = movie.director_names or details.get("director_names", "")
        movie.writer_names = movie.writer_names or details.get("writer_names", "")
        movie.backdrop_url = movie.backdrop_url or movie.poster_url
        movie.justwatch_url = details["justwatch_url"]
        movie.data_source = "curated"

        bookmyshow_links = bookmyshow_links_for_title(title)
        movie.bookmyshow_movie_url = bookmyshow_links["movie"]
        movie.bookmyshow_ticket_url = bookmyshow_links["ticket"]
        movie.bookmyshow_url = bookmyshow_links["primary"]

    db.session.commit()


def sync_booking_catalog_from_tmdb(force=False):
    settings = SystemSetting.query.first()
    today_key = datetime.utcnow().strftime("%Y-%m-%d")

    if not settings:
        return False

    if not force and settings.tmdb_last_sync == today_key:
        return False

    try:
        tmdb_movies = fetch_booking_catalog_from_tmdb()
    except Exception as error:
        print("TMDb sync failed:", error)
        return False

    if not tmdb_movies:
        return False

    theater_seed = THEATER_NETWORK[:8]

    theaters = []

    for name, city, address, total_screens, *_ in theater_seed:
        theater = Theater.query.filter_by(name=name, city=city).first()

        if not theater:
            theater = Theater(
                name=name,
                city=city,
                address=address,
                total_screens=total_screens
            )
            db.session.add(theater)
            db.session.flush()
        else:
            theater.address = address
            theater.total_screens = total_screens

        for index in range(1, total_screens + 1):
            ensure_screen(theater, f"Screen {index}", 96 + (index * 18))

        theaters.append(theater)

    db.session.flush()

    movies = []

    for item in tmdb_movies:
        movie = Movie.query.filter_by(tmdb_id=item["tmdb_id"]).first()

        if not movie:
            movie = Movie.query.filter_by(title=item["title"]).first()

        if not movie:
            movie = Movie(title=item["title"], description=item["description"])
            db.session.add(movie)

        movie.title = item["title"]
        movie.description = item["description"]
        movie.poster_url = item["poster_url"]
        movie.backdrop_url = item.get("backdrop_url") or item["poster_url"]
        movie.language = item["language"]
        movie.genre = item["genre"]
        movie.release_date = item["release_date"]
        movie.rating = item["rating"]
        movie.tmdb_id = item["tmdb_id"]
        movie.tmdb_url = f"https://www.themoviedb.org/movie/{item['tmdb_id']}"
        movie.data_source = "tmdb"

        encoded_title = quote_plus(item["title"])
        bookmyshow_links = bookmyshow_links_for_title(item["title"])
        movie.bookmyshow_movie_url = bookmyshow_links["movie"]
        movie.bookmyshow_ticket_url = bookmyshow_links["ticket"]
        movie.bookmyshow_url = bookmyshow_links["primary"]
        movie.justwatch_url = f"https://www.justwatch.com/in/search?q={encoded_title}"
        movies.append(movie)

    db.session.flush()

    base_day = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    show_times = ("10:30", "13:45", "17:15", "20:45")
    prices = (180, 220, 260, 320)

    for movie_index, movie in enumerate(movies[:16]):
        for slot_index in range(2):
            theater = theaters[(movie_index + slot_index) % len(theaters)]
            screens = Screen.query.filter_by(theater_id=theater.id).order_by(Screen.id.asc()).all()
            screen = screens[slot_index % len(screens)]
            day = base_day + timedelta(days=movie_index % 5)
            show_time = f"{day.date()} {show_times[(movie_index + slot_index) % len(show_times)]}"

            existing_show = Show.query.filter_by(
                movie_id=movie.id,
                theater_id=theater.id,
                screen_id=screen.id,
                show_time=show_time
            ).first()

            if existing_show:
                existing_show.price = prices[(movie_index + slot_index) % len(prices)]
                continue

            db.session.add(
                Show(
                    movie_id=movie.id,
                    theater_id=theater.id,
                    screen_id=screen.id,
                    show_time=show_time,
                    price=prices[(movie_index + slot_index) % len(prices)]
                )
            )

    settings.tmdb_last_sync = today_key
    db.session.commit()
    return True


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

        if "booked_at" not in booking_columns:
            connection.exec_driver_sql("ALTER TABLE bookings ADD COLUMN booked_at DATETIME")

        if "cancelled_at" not in booking_columns:
            connection.exec_driver_sql("ALTER TABLE bookings ADD COLUMN cancelled_at DATETIME")

        if "external_booking_url" not in booking_columns:
            connection.exec_driver_sql("ALTER TABLE bookings ADD COLUMN external_booking_url VARCHAR(500)")

        if "booking_id" not in ticket_columns:
            connection.exec_driver_sql("ALTER TABLE tickets ADD COLUMN booking_id INTEGER")

        if "trailer_url" not in movie_columns:
            connection.exec_driver_sql("ALTER TABLE movies ADD COLUMN trailer_url VARCHAR(300)")

        movie_updates = {
            "justwatch_url": "ALTER TABLE movies ADD COLUMN justwatch_url VARCHAR(300)",
            "bookmyshow_url": "ALTER TABLE movies ADD COLUMN bookmyshow_url VARCHAR(300)",
            "bookmyshow_movie_url": "ALTER TABLE movies ADD COLUMN bookmyshow_movie_url VARCHAR(300)",
            "bookmyshow_ticket_url": "ALTER TABLE movies ADD COLUMN bookmyshow_ticket_url VARCHAR(300)",
            "tmdb_id": "ALTER TABLE movies ADD COLUMN tmdb_id INTEGER",
            "tmdb_url": "ALTER TABLE movies ADD COLUMN tmdb_url VARCHAR(300)",
            "data_source": "ALTER TABLE movies ADD COLUMN data_source VARCHAR(50) DEFAULT 'manual'",
            "runtime_minutes": "ALTER TABLE movies ADD COLUMN runtime_minutes INTEGER",
            "certificate": "ALTER TABLE movies ADD COLUMN certificate VARCHAR(20)",
            "cast_names": "ALTER TABLE movies ADD COLUMN cast_names TEXT",
            "director_names": "ALTER TABLE movies ADD COLUMN director_names TEXT",
            "writer_names": "ALTER TABLE movies ADD COLUMN writer_names TEXT",
            "backdrop_url": "ALTER TABLE movies ADD COLUMN backdrop_url VARCHAR(500)",
        }

        for column, statement in movie_updates.items():
            if column not in movie_columns:
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


@app.before_request
def refresh_booking_catalog_daily():
    if request.endpoint not in {"home", "movie_bp.movies", "show_bp.shows"}:
        return None

    today_key = datetime.utcnow().strftime("%Y-%m-%d")

    if app.config.get("CATALOG_SYNC_ATTEMPT_DATE") == today_key:
        return None

    app.config["CATALOG_SYNC_ATTEMPT_DATE"] = today_key

    if not sync_booking_catalog_from_tmdb():
        sync_booking_catalog_from_imdbapi()

    backfill_missing_movie_posters(limit=12)

    return None


with app.app_context():
    db.create_all()
    ensure_schema_updates()
    create_default_settings()
    create_default_admin()
    sync_theater_network()
    if not sync_booking_catalog_from_tmdb() and not sync_booking_catalog_from_imdbapi():
        sync_curated_upcoming_catalog()
    apply_featured_movie_details()
    backfill_missing_movie_posters(limit=12)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
