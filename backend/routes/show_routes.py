from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for
from auth.guards import admin_required
from extensions import db
from models.movie import Movie
from models.theater import Theater, Screen
from models.show import Show
from services.activity_service import log_activity

show_bp = Blueprint("show_bp", __name__)

LEGACY_DEMO_MOVIES = (
    "Dune: Part Two",
    "Inside Out 2",
    "Furiosa: A Mad Max Saga",
    "Aavesham",
    "Kalki 2898 AD",
    "Munjya",
)


def pagination_window(current_page, total_pages, radius=2):
    if total_pages <= 1:
        return []

    current_page = max(1, min(current_page, total_pages))
    pages = {1, total_pages}

    for page_number in range(current_page - radius, current_page + radius + 1):
        if 1 <= page_number <= total_pages:
            pages.add(page_number)

    ordered_pages = sorted(pages)
    window = []
    previous = None

    for page_number in ordered_pages:
        if previous is not None and page_number - previous > 1:
            window.append(None)

        window.append(page_number)
        previous = page_number

    return window


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
        log_activity("Show Added", f"Added show #{show.id} for movie #{show.movie_id}", notify=True)

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
    selected_page = max(request.args.get("page", 1, type=int), 1)
    per_page = 24
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

    total_movies = len(movie_cards)
    total_pages = max((total_movies + per_page - 1) // per_page, 1)
    selected_page = min(selected_page, total_pages)
    start_index = (selected_page - 1) * per_page
    movie_cards = movie_cards[start_index:start_index + per_page]

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
        selected_language=selected_language,
        selected_page=selected_page,
        total_pages=total_pages,
        pagination_pages=pagination_window(selected_page, total_pages)
    )
