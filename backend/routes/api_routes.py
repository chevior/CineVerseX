from flask import Blueprint, jsonify

from models.movie import Movie
from models.show import Show
from models.theater import Theater
from services.catalog_data import BOOKMYSHOW_HOME_URL

api_bp = Blueprint("api_bp", __name__, url_prefix="/api")


def movie_json(movie):
    return {
        "id": movie.id,
        "title": movie.title,
        "language": movie.language,
        "genre": movie.genre,
        "release_date": movie.release_date,
        "rating": movie.rating,
        "poster_url": movie.poster_url,
        "bookmyshow_url": BOOKMYSHOW_HOME_URL,
        "justwatch_url": movie.justwatch_url,
    }


@api_bp.route("/movies")
def movies():
    rows = Movie.query.order_by(Movie.release_date.desc(), Movie.title.asc()).limit(100).all()
    return jsonify([movie_json(movie) for movie in rows])


@api_bp.route("/movies/<int:movie_id>")
def movie_details(movie_id):
    movie = Movie.query.get_or_404(movie_id)
    data = movie_json(movie)
    data["description"] = movie.description
    data["runtime_minutes"] = movie.runtime_minutes
    data["certificate"] = movie.certificate
    data["trailer_url"] = movie.trailer_url
    return jsonify(data)


@api_bp.route("/theaters")
def theaters():
    rows = Theater.query.filter(Theater.name != "BookMyShow").order_by(Theater.city.asc(), Theater.name.asc()).limit(200).all()
    return jsonify([
        {
            "id": theater.id,
            "name": theater.name,
            "city": theater.city,
            "address": theater.address,
            "total_screens": theater.total_screens,
        }
        for theater in rows
    ])


@api_bp.route("/shows")
def shows():
    rows = Show.query.order_by(Show.show_time.asc()).limit(200).all()
    return jsonify([
        {
            "id": show.id,
            "movie_id": show.movie_id,
            "movie": show.movie.title if show.movie else "",
            "theater_id": show.theater_id,
            "theater": show.theater.name if show.theater else "",
            "screen_id": show.screen_id,
            "show_time": show.show_time,
            "price": show.price,
        }
        for show in rows
    ])


@api_bp.route("/upcoming")
def upcoming():
    rows = Movie.query.filter(Movie.release_date >= "2026-01-01").order_by(Movie.release_date.asc()).limit(100).all()
    return jsonify([movie_json(movie) for movie in rows])


@api_bp.route("/trending")
def trending():
    rows = Movie.query.order_by(Movie.rating.desc(), Movie.title.asc()).limit(50).all()
    return jsonify([movie_json(movie) for movie in rows])
