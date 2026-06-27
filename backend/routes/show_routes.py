from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for
from auth.guards import admin_required
from extensions import db
from models.movie import Movie
from models.theater import Theater, Screen
from models.show import Show

show_bp = Blueprint("show_bp", __name__)

LEGACY_DEMO_MOVIES = (
    "Dune: Part Two",
    "Inside Out 2",
    "Furiosa: A Mad Max Saga",
    "Aavesham",
    "Kalki 2898 AD",
    "Munjya",
)


@show_bp.route("/add-show", methods=["GET", "POST"])
@admin_required
def add_show():
    if request.method == "POST":
        theater_id = int(request.form["theater_id"])
        screen_id = int(request.form["screen_id"])

        screen = Screen.query.get_or_404(screen_id)
        if screen.theater_id != theater_id:
            return "Selected screen does not belong to the selected theater", 400

        show = Show(
            movie_id=int(request.form["movie_id"]),
            theater_id=theater_id,
            screen_id=screen_id,
            show_time=request.form["show_time"],
            price=float(request.form["price"])
        )

        db.session.add(show)
        db.session.commit()

        return redirect(url_for("show_bp.shows"))

    return render_template(
        "add_show.html",
        movies=Movie.query.all(),
        theaters=Theater.query.all(),
        screens=Screen.query.all()
    )


@show_bp.route("/shows")
def shows():
    selected_sort = request.args.get("sort", "release")
    selected_genre = request.args.get("genre", "")
    selected_language = request.args.get("language", "")
    today_key = datetime.utcnow().strftime("%Y-%m-%d")

    query = (
        Show.query
        .join(Movie)
        .join(Theater)
        .filter(~Movie.title.in_(LEGACY_DEMO_MOVIES))
        .filter(Movie.data_source.in_(("tmdb", "imdbapi", "curated")))
        .filter(Show.show_time >= today_key)
    )

    if selected_genre:
        query = query.filter(Movie.genre.ilike(f"%{selected_genre}%"))

    if selected_language:
        query = query.filter(Movie.language.ilike(f"%{selected_language}%"))

    poster_query = query.filter(Movie.poster_url.isnot(None), Movie.poster_url != "")

    if poster_query.count() >= 24:
        query = poster_query

    poster_first = Movie.poster_url.isnot(None).desc(), (Movie.poster_url != "").desc()

    if selected_sort == "movie":
        query = query.order_by(*poster_first, Movie.title.asc(), Movie.release_date.asc(), Show.show_time.asc())
    elif selected_sort == "rating":
        query = query.order_by(*poster_first, Movie.rating.desc(), Movie.release_date.asc(), Show.show_time.asc())
    else:
        query = query.order_by(*poster_first, Movie.release_date.asc(), Show.show_time.asc())

    movie_cards = []
    seen_movie_ids = set()

    for show in query.all():
        if not show.movie or show.movie_id in seen_movie_ids:
            continue

        seen_movie_ids.add(show.movie_id)
        movie_cards.append({
            "movie": show.movie,
            "show": show,
        })

    return render_template(
        "shows.html",
        movie_cards=movie_cards,
        genres=[
            "Action",
            "Adventure",
            "Animation",
            "Biography",
            "Comedy",
            "Crime",
            "Drama",
            "Family",
            "Fantasy",
            "History",
            "Horror",
            "Mystery",
            "Sci-Fi",
            "Superhero",
            "Thriller",
        ],
        languages=[
            "English",
            "Hindi",
            "Telugu",
            "Tamil",
            "Kannada",
            "Malayalam",
            "Marathi",
            "Punjabi",
            "Gujarati",
            "Korean",
        ],
        selected_sort=selected_sort,
        selected_genre=selected_genre,
        selected_language=selected_language
    )
