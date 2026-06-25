from flask import Blueprint, render_template, request

from extensions import db
from models.movie import Movie
from models.theater import Theater, Screen
from models.show import Show

show_bp = Blueprint("show_bp", __name__)


@show_bp.route("/add-show", methods=["GET", "POST"])
def add_show():
    if request.method == "POST":
        show = Show(
            movie_id=int(request.form["movie_id"]),
            theater_id=int(request.form["theater_id"]),
            screen_id=int(request.form["screen_id"]),
            show_time=request.form["show_time"],
            price=float(request.form["price"])
        )

        db.session.add(show)
        db.session.commit()

        return "Show Added Successfully"

    return render_template(
        "add_show.html",
        movies=Movie.query.all(),
        theaters=Theater.query.all(),
        screens=Screen.query.all()
    )


@show_bp.route("/shows")
def shows():
    all_shows = Show.query.all()
    return render_template("shows.html", shows=all_shows)