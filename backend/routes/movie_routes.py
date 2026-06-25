import os
from uuid import uuid4

from flask import Blueprint, render_template, request, current_app
from werkzeug.utils import secure_filename

from extensions import db
from models.movie import Movie
from models.show import Show
from models.theater import Theater

movie_bp = Blueprint("movie_bp", __name__)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


@movie_bp.route("/movies")
def movies():
    all_movies = Movie.query.all()
    return render_template("movies.html", movies=all_movies)


@movie_bp.route("/add-movie", methods=["GET", "POST"])
def add_movie():

    if request.method == "POST":

        title = request.form["title"].strip()
        description = request.form["description"].strip()
        language = request.form["language"].strip()
        genre = request.form["genre"].strip()
        release_date = request.form["release_date"].strip()
        rating = float(request.form["rating"] or 0)

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
            rating=rating
        )

        db.session.add(movie)
        db.session.commit()

        return "Movie Added Successfully"

    return render_template("add_movie.html")


@movie_bp.route("/movie/<int:movie_id>")
def movie_details(movie_id):

    movie = Movie.query.get_or_404(movie_id)

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
        theaters=theaters
    )
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
def edit_movie(movie_id):

    movie = Movie.query.get_or_404(movie_id)

    if request.method == "POST":

        movie.title = request.form["title"]
        movie.description = request.form["description"]
        movie.language = request.form["language"]
        movie.genre = request.form["genre"]
        movie.release_date = request.form["release_date"]
        movie.rating = float(request.form["rating"])

        db.session.commit()

        return "Movie Updated Successfully"

    return render_template(
        "edit_movie.html",
        movie=movie
    )
@movie_bp.route("/delete-movie/<int:movie_id>")
def delete_movie(movie_id):

    movie = Movie.query.get_or_404(movie_id)

    db.session.delete(movie)
    db.session.commit()

    return "Movie Deleted Successfully"