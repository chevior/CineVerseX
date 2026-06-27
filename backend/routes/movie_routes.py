import os
import json
import sqlite3
from datetime import datetime
from urllib.parse import parse_qs, quote_plus, urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from flask import Blueprint, flash, render_template, request, current_app, redirect, url_for
from flask_login import current_user
from sqlalchemy import func
from werkzeug.utils import secure_filename

from auth.guards import admin_required, login_required
from extensions import db
from models.movie import Movie
from models.review import Review
from models.show import Show
from models.theater import Theater

movie_bp = Blueprint("movie_bp", __name__)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
GENRES = [
    "Action",
    "Adventure",
    "Biography",
    "Comedy",
    "Crime",
    "Documentary",
    "Drama",
    "Family",
    "Fantasy",
    "History",
    "Music",
    "Mystery",
    "Romance",
    "Thriller",
    "Horror",
    "Animation",
    "Sci-Fi",
    "War",
    "Western",
]


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def imdb_db_path():
    configured_path = current_app.config.get("IMDB_DB_PATH", "").strip()

    if configured_path:
        return os.path.abspath(configured_path)

    default_path = os.path.abspath(
        os.path.join(current_app.root_path, "..", "cineversex.db")
    )

    deploy_disk_path = os.path.abspath("/var/data/cineversex.db")

    if os.path.isfile(deploy_disk_path):
        return deploy_disk_path

    return default_path


def imdb_db_available():
    return os.path.isfile(imdb_db_path())


def bookmyshow_search_url(title, city="bengaluru"):
    return "https://in.bookmyshow.com/"


def justwatch_search_url(title):
    return f"https://www.justwatch.com/in/search?q={quote_plus(title or '')}"


def imdb_id_from_url(url):
    if not url:
        return ""

    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]

    for part in parts:
        if part.startswith("tt") and part[2:].isdigit():
            return part

    return ""


def enrich_movie_from_imdbapi(movie):
    imdb_id = imdb_id_from_url(movie.tmdb_url)

    if not imdb_id or movie.cast_names:
        return

    try:
        request = Request(
            f"https://api.imdbapi.dev/titles/{imdb_id}",
            headers={
                "accept": "application/json",
                "User-Agent": "CineVerseX/1.0 (+https://cineversex.onrender.com)",
            }
        )

        with urlopen(request, timeout=10) as response:
            details = json.loads(response.read().decode("utf-8"))
    except Exception as error:
        print("IMDbAPI detail enrich failed:", error)
        return

    runtime_seconds = details.get("runtimeSeconds") or 0
    primary_image = details.get("primaryImage") or {}

    movie.description = details.get("plot") or movie.description
    movie.runtime_minutes = movie.runtime_minutes or (int(runtime_seconds // 60) if runtime_seconds else None)
    movie.backdrop_url = movie.backdrop_url or primary_image.get("url") or movie.poster_url
    movie.cast_names = ", ".join(
        person.get("displayName", "")
        for person in details.get("stars", [])[:10]
        if person.get("displayName")
    )
    movie.director_names = ", ".join(
        person.get("displayName", "")
        for person in details.get("directors", [])[:4]
        if person.get("displayName")
    )
    movie.writer_names = ", ".join(
        person.get("displayName", "")
        for person in details.get("writers", [])[:4]
        if person.get("displayName")
    )

    db.session.commit()


def fetch_imdb_movies(genre="", view="", sort="popular", limit=50):
    conn = sqlite3.connect(f"file:{imdb_db_path()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    base_query = """
        SELECT *
        FROM (
            SELECT
                t.tconst,
                t.primaryTitle,
                t.originalTitle,
                t.startYear,
                t.runtimeMinutes,
                t.genres,
                r.averageRating,
                r.numVotes,
                ROW_NUMBER() OVER (
                    PARTITION BY LOWER(TRIM(t.primaryTitle)), CAST(t.startYear AS INTEGER)
                    ORDER BY COALESCE(r.numVotes, 0) DESC, t.tconst ASC
                ) AS title_rank
            FROM imdb_titles t
            LEFT JOIN imdb_ratings r ON t.tconst = r.tconst
            WHERE t.titleType = 'movie'
            AND t.isAdult = 0
    """

    params = []

    if genre:
        base_query += " AND t.genres LIKE ?"
        params.append(f"%{genre}%")

    if view == "now-showing":
        base_query += " AND CAST(t.startYear AS INTEGER) = 2026"
    elif view == "upcoming":
        base_query += " AND CAST(t.startYear AS INTEGER) >= 2026"

    base_query += """
        )
        WHERE title_rank = 1
    """

    sort_clauses = {
        "rating": "COALESCE(averageRating, 0) DESC, COALESCE(numVotes, 0) DESC",
        "newest": "COALESCE(startYear, 0) DESC, COALESCE(numVotes, 0) DESC",
        "title": "primaryTitle COLLATE NOCASE ASC",
        "popular": "COALESCE(numVotes, 0) DESC, COALESCE(averageRating, 0) DESC",
    }

    base_query += f"""
        ORDER BY {sort_clauses.get(sort, sort_clauses["popular"])}
        LIMIT ?
    """
    params.append(limit * 4)

    cur.execute(base_query, params)
    rows = cur.fetchall()
    conn.close()

    movies = []
    seen_titles = set()

    for row in rows:
        title_key = (
            (row["primaryTitle"] or "").strip().casefold(),
            int(row["startYear"] or 0)
        )

        if title_key in seen_titles:
            continue

        seen_titles.add(title_key)
        movies.append(row)

        if len(movies) >= limit:
            break

    return movies


def fetch_imdb_movie(tconst):
    conn = sqlite3.connect(f"file:{imdb_db_path()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            t.tconst,
            t.primaryTitle,
            t.originalTitle,
            t.startYear,
            t.runtimeMinutes,
            t.genres,
            r.averageRating,
            r.numVotes
        FROM imdb_titles t
        LEFT JOIN imdb_ratings r ON t.tconst = r.tconst
        WHERE t.tconst = ?
        """,
        (tconst,)
    )
    movie = cur.fetchone()
    conn.close()

    return movie


@movie_bp.route("/movies")
def movies():
    selected_genre = request.args.get("genre", "")
    selected_view = request.args.get("view", "upcoming")
    selected_sort = request.args.get("sort", "popular")
    today_key = datetime.utcnow().strftime("%Y-%m-%d")

    local_query = Movie.query.filter(Movie.data_source.in_(("tmdb", "imdbapi", "curated")))

    if local_query.count() > 0:
        if selected_genre:
            local_query = local_query.filter(Movie.genre.ilike(f"%{selected_genre}%"))

        if selected_view == "now-showing":
            local_query = local_query.filter(Movie.release_date <= today_key)
        elif selected_view == "upcoming":
            local_query = local_query.filter(Movie.release_date >= today_key)

        poster_query = local_query.filter(Movie.poster_url.isnot(None), Movie.poster_url != "")

        if poster_query.count() >= 24:
            local_query = poster_query

        poster_first = Movie.poster_url.isnot(None).desc(), (Movie.poster_url != "").desc()

        if selected_sort == "rating":
            local_query = local_query.order_by(*poster_first, Movie.rating.desc(), Movie.title.asc())
        elif selected_sort == "newest":
            local_query = local_query.order_by(*poster_first, Movie.release_date.desc(), Movie.rating.desc())
        elif selected_sort == "title":
            local_query = local_query.order_by(*poster_first, Movie.title.asc())
        else:
            local_query = local_query.order_by(*poster_first, Movie.release_date.asc(), Movie.rating.desc())

        return render_template(
            "movies.html",
            movies=local_query.limit(80).all(),
            genres=GENRES,
            selected_genre=selected_genre,
            selected_view=selected_view,
            selected_sort=selected_sort,
            movie_source="local"
        )

    if imdb_db_available():
        imdb_movies = fetch_imdb_movies(selected_genre, selected_view, selected_sort)
        return render_template(
            "movies.html",
            movies=imdb_movies,
            genres=GENRES,
            selected_genre=selected_genre,
            selected_view=selected_view,
            selected_sort=selected_sort,
            movie_source="imdb",
            bookmyshow_search_url=bookmyshow_search_url
        )

    return render_template(
        "movies.html",
        movies=[],
        genres=GENRES,
        selected_genre=selected_genre,
        selected_view=selected_view,
        selected_sort=selected_sort,
        movie_source="imdb",
        bookmyshow_search_url=bookmyshow_search_url,
        imdb_status_message=(
            "IMDb database is not connected. "
            f"Expected database path: {imdb_db_path()}"
        )
    )


@movie_bp.route("/imdb/movie/<tconst>")
def imdb_movie_details(tconst):
    if not imdb_db_available():
        return "IMDb database not found", 404

    movie = fetch_imdb_movie(tconst)

    if not movie:
        return "IMDb movie not found", 404

    return render_template(
        "imdb_movie_details.html",
        movie=movie,
        bookmyshow_url=bookmyshow_search_url(movie["primaryTitle"]),
        justwatch_url=justwatch_search_url(movie["primaryTitle"])
    )


def normalize_youtube_embed_url(url):
    url = (url or "").strip()

    if not url:
        return ""

    parsed = urlparse(url)
    host = parsed.netloc.lower().replace("www.", "")
    video_id = ""

    if host in {"youtube.com", "m.youtube.com"}:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif parsed.path.startswith("/embed/"):
            video_id = parsed.path.split("/embed/", 1)[1].split("/", 1)[0]
        elif parsed.path.startswith("/shorts/"):
            video_id = parsed.path.split("/shorts/", 1)[1].split("/", 1)[0]
    elif host == "youtu.be":
        video_id = parsed.path.strip("/").split("/", 1)[0]

    if video_id:
        return f"https://www.youtube.com/embed/{video_id}"

    return url


def youtube_watch_url(embed_url):
    embed_url = (embed_url or "").strip()

    if "/embed/" not in embed_url:
        return embed_url

    video_id = embed_url.split("/embed/", 1)[1].split("?", 1)[0].split("/", 1)[0]
    return f"https://www.youtube.com/watch?v={video_id}"


@movie_bp.route("/add-movie", methods=["GET", "POST"])
@admin_required
def add_movie():

    if request.method == "POST":

        title = request.form["title"].strip()
        description = request.form["description"].strip()
        language = request.form["language"].strip()
        genre = request.form.get("genre", "").strip()
        release_date = request.form["release_date"].strip()
        rating = float(request.form["rating"] or 0)
        trailer_url = normalize_youtube_embed_url(request.form.get("trailer_url"))
        justwatch_url = (request.form.get("justwatch_url") or "").strip()
        bookmyshow_url = (request.form.get("bookmyshow_url") or "").strip()

        existing_movie = Movie.query.filter_by(title=title).first()

        if existing_movie:
            return "Movie already exists"

        poster_file = request.files.get("poster")
        poster_url = ""

        if poster_file and poster_file.filename:
            if not allowed_file(poster_file.filename):
                return "Only PNG, JPG, JPEG, and WEBP images are allowed"

            original_filename = secure_filename(poster_file.filename)
            extension = original_filename.rsplit(".", 1)[1].lower()
            unique_filename = f"{uuid4().hex}.{extension}"

            poster_folder = os.path.join(
                current_app.root_path,
                "static",
                "posters"
            )

            if not os.path.isdir(poster_folder):
                os.makedirs(poster_folder)

            poster_path = os.path.join(
                poster_folder,
                unique_filename
            )

            poster_file.save(poster_path)

            poster_url = f"posters/{unique_filename}"

        movie = Movie(
            title=title,
            description=description,
            poster_url=poster_url,
            language=language,
            genre=genre,
            release_date=release_date,
            rating=rating,
            trailer_url=trailer_url,
            justwatch_url=justwatch_url,
            bookmyshow_url=bookmyshow_url
        )

        if not movie.poster_url:
            return "Please upload a poster image"

        db.session.add(movie)
        db.session.commit()

        return redirect(url_for("movie_bp.movies"))

    return render_template("add_movie.html")


@movie_bp.route("/movie/<int:movie_id>")
def movie_details(movie_id):

    movie = Movie.query.get_or_404(movie_id)
    enrich_movie_from_imdbapi(movie)
    reviews = Review.query.filter_by(movie_id=movie_id)\
        .order_by(Review.created_at.desc())\
        .all()
    avg_rating = db.session.query(
        func.avg(Review.rating)
    ).filter_by(movie_id=movie_id).scalar()

    shows = Show.query.filter_by(
        movie_id=movie.id
    ).all()

    similar_movies = Movie.query.filter(
        Movie.id != movie.id,
        Movie.genre.ilike(f"%{(movie.genre or '').split(',')[0].strip()}%")
    ).order_by(Movie.rating.desc()).limit(4).all() if movie.genre else []

    theaters = {}

    for show in shows:
        theater = Theater.query.get(show.theater_id)

        if theater:
            if theater.id not in theaters:
                theaters[theater.id] = {
                    "theater": theater,
                    "shows": []
                }

            theaters[theater.id]["shows"].append(show)

    return render_template(
        "movie_details.html",
        movie=movie,
        theaters=theaters,
        reviews=reviews,
        avg_rating=round(avg_rating, 1) if avg_rating else 0,
        trailer_watch_url=youtube_watch_url(movie.trailer_url),
        similar_movies=similar_movies,
        justwatch_url=movie.justwatch_url or justwatch_search_url(movie.title)
    )


@movie_bp.route("/movie/<int:movie_id>/review", methods=["POST"])
@login_required
def add_review(movie_id):
    Movie.query.get_or_404(movie_id)

    try:
        rating = int(request.form.get("rating", 0))
    except ValueError:
        rating = 0

    comment = (request.form.get("comment") or "").strip()

    if rating < 1 or rating > 5:
        flash("Rating must be between 1 and 5.", "danger")
        return redirect(url_for("movie_bp.movie_details", movie_id=movie_id))

    existing_review = Review.query.filter_by(
        user_id=current_user.id,
        movie_id=movie_id
    ).first()

    if existing_review:
        existing_review.rating = rating
        existing_review.comment = comment
    else:
        review = Review(
            user_id=current_user.id,
            movie_id=movie_id,
            rating=rating,
            comment=comment
        )
        db.session.add(review)

    db.session.commit()
    flash("Review submitted successfully.", "success")
    return redirect(url_for("movie_bp.movie_details", movie_id=movie_id))


@movie_bp.route("/search")
def search_movies():

    query = request.args.get("q", "")

    movies = Movie.query.filter(
        Movie.title.ilike(f"%{query}%")
    ).all()

    return render_template(
        "search_results.html",
        movies=movies,
        query=query
    )
@movie_bp.route("/edit-movie/<int:movie_id>", methods=["GET", "POST"])
@admin_required
def edit_movie(movie_id):

    movie = Movie.query.get_or_404(movie_id)

    if request.method == "POST":

        movie.title = request.form["title"]
        movie.description = request.form["description"]
        movie.language = request.form["language"]
        movie.genre = request.form.get("genre", "").strip()
        movie.release_date = request.form["release_date"]
        movie.rating = float(request.form["rating"])
        movie.trailer_url = normalize_youtube_embed_url(request.form.get("trailer_url"))
        movie.justwatch_url = (request.form.get("justwatch_url") or "").strip()
        movie.bookmyshow_url = (request.form.get("bookmyshow_url") or "").strip()

        db.session.commit()

        return redirect(url_for("movie_bp.movie_details", movie_id=movie.id))

    return render_template(
        "edit_movie.html",
        movie=movie,
        genres=GENRES,
        trailer_watch_url=youtube_watch_url(movie.trailer_url)
    )
@movie_bp.route("/delete-movie/<int:movie_id>")
@admin_required
def delete_movie(movie_id):

    movie = Movie.query.get_or_404(movie_id)

    db.session.delete(movie)
    db.session.commit()

    return redirect(url_for("movie_bp.movies"))
