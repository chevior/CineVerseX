import os
import json
from urllib.parse import parse_qs, urlencode, urlparse
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
    "Comedy",
    "Drama",
    "Romance",
    "Thriller",
    "Horror",
    "Animation",
    "Sci-Fi",
]


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


@movie_bp.route("/movies")
def movies():
    selected_genre = request.args.get("genre", "")
    query = Movie.query

    if selected_genre:
        query = query.filter(Movie.genre.ilike(f"%{selected_genre}%"))

    all_movies = query.all()

    return render_template(
        "movies.html",
        movies=all_movies,
        genres=GENRES,
        selected_genre=selected_genre
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


def fetch_json(url, headers=None):
    request = Request(url, headers=headers or {})

    with urlopen(request, timeout=12) as response:
        return json.loads(response.read().decode("utf-8"))


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

    query = urlencode(params)
    suffix = f"?{query}" if query else ""
    return f"https://api.themoviedb.org/3{path}{suffix}"


def tmdb_is_configured():
    return bool(
        os.environ.get("TMDB_API_KEY", "").strip()
        or os.environ.get("TMDB_BEARER_TOKEN", "").strip()
    )


def tmdb_movie_details(tmdb_id):
    return fetch_json(
        tmdb_url(
            f"/movie/{tmdb_id}",
            {
                "language": "en-US",
                "append_to_response": "external_ids,videos",
            }
        ),
        headers=tmdb_headers()
    )


def tmdb_trailer_url(details):
    videos = details.get("videos", {}).get("results", [])

    for video in videos:
        if (
            video.get("site") == "YouTube"
            and video.get("type") == "Trailer"
            and video.get("key")
        ):
            return normalize_youtube_embed_url(
                f"https://www.youtube.com/watch?v={video['key']}"
            )

    return ""


def import_tmdb_popular_movies(pages=1, region="IN"):
    if not tmdb_is_configured():
        return 0, "Set TMDB_API_KEY or TMDB_BEARER_TOKEN first."

    imported_count = 0
    pages = max(1, min(int(pages or 1), 5))

    for page in range(1, pages + 1):
        popular = fetch_json(
            tmdb_url(
                "/movie/popular",
                {
                    "language": "en-US",
                    "page": page,
                    "region": region,
                }
            ),
            headers=tmdb_headers()
        )

        for item in popular.get("results", []):
            details = tmdb_movie_details(item["id"])
            title = details.get("title") or item.get("title")

            if not title:
                continue

            movie = Movie.query.filter_by(title=title).first()
            if not movie:
                movie = Movie(title=title, description="")
                db.session.add(movie)
                imported_count += 1

            poster_path = details.get("poster_path") or item.get("poster_path")
            genres = ", ".join(genre["name"] for genre in details.get("genres", []))
            release_date = details.get("release_date") or item.get("release_date") or ""

            movie.description = details.get("overview") or item.get("overview") or movie.description
            movie.poster_url = (
                f"https://image.tmdb.org/t/p/w500{poster_path}"
                if poster_path
                else movie.poster_url
            )
            movie.language = (details.get("original_language") or "").upper()
            movie.genre = genres or movie.genre
            movie.release_date = release_date[:4] if release_date else movie.release_date
            movie.rating = round(float(details.get("vote_average") or item.get("vote_average") or 0), 1)
            movie.trailer_url = tmdb_trailer_url(details) or movie.trailer_url
            movie.tmdb_id = details.get("id") or item.get("id") or movie.tmdb_id
            movie.tmdb_url = (
                f"https://www.themoviedb.org/movie/{movie.tmdb_id}"
                if movie.tmdb_id
                else movie.tmdb_url
            )
            movie.justwatch_url = (
                movie.justwatch_url
                or f"https://www.justwatch.com/in/search?q={urlencode({'q': title}).split('=', 1)[1]}"
            )

    db.session.commit()
    return imported_count, f"Imported or refreshed TMDb popular movies from {pages} page(s)."


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
        tmdb_url_value = (request.form.get("tmdb_url") or "").strip()
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
            tmdb_url=tmdb_url_value,
            justwatch_url=justwatch_url,
            bookmyshow_url=bookmyshow_url
        )

        if not movie.poster_url:
            return "Please upload a poster image"

        db.session.add(movie)
        db.session.commit()

        return redirect(url_for("movie_bp.movies"))

    return render_template("add_movie.html")


@movie_bp.route("/admin/import-tmdb-movies", methods=["POST"])
@admin_required
def import_tmdb_movies():
    pages = request.form.get("pages", 1)

    try:
        imported_count, message = import_tmdb_popular_movies(pages=pages)
        category = "success" if imported_count or tmdb_is_configured() else "warning"
        flash(message, category)
    except Exception as error:
        flash(f"TMDb import failed: {error}", "danger")

    return redirect(url_for("movie_bp.movies"))


@movie_bp.route("/movie/<int:movie_id>")
def movie_details(movie_id):

    movie = Movie.query.get_or_404(movie_id)
    reviews = Review.query.filter_by(movie_id=movie_id)\
        .order_by(Review.created_at.desc())\
        .all()
    avg_rating = db.session.query(
        func.avg(Review.rating)
    ).filter_by(movie_id=movie_id).scalar()

    shows = Show.query.filter_by(
        movie_id=movie.id
    ).all()

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
        trailer_watch_url=youtube_watch_url(movie.trailer_url)
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
        movie.tmdb_url = (request.form.get("tmdb_url") or "").strip()
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
