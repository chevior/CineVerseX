import os
from urllib.parse import parse_qs, urlparse
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
        query = query.filter_by(genre=selected_genre)

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

        existing_movie = Movie.query.filter_by(title=title).first()

        if existing_movie:
            return "Movie already exists"

        poster_file = request.files.get("poster")

        if not poster_file or poster_file.filename == "":
            return "Please upload a poster image"

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
            trailer_url=trailer_url
        )

        db.session.add(movie)
        db.session.commit()

        return redirect(url_for("movie_bp.movies"))

    return render_template("add_movie.html")


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
