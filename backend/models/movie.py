from datetime import datetime
from extensions import db


class Movie(db.Model):
    __tablename__ = "movies"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    title = db.Column(
        db.String(200),
        nullable=False
    )

    description = db.Column(
        db.Text,
        nullable=False
    )

    poster_url = db.Column(
        db.String(500)
    )

    language = db.Column(
        db.String(50)
    )

    genre = db.Column(db.String(100), nullable=True)

    release_date = db.Column(
        db.String(50)
    )

    rating = db.Column(
        db.Float,
        default=0
    )

    trailer_url = db.Column(db.String(300))
    tmdb_id = db.Column(db.Integer)
    tmdb_url = db.Column(db.String(300))
    justwatch_url = db.Column(db.String(300))
    bookmyshow_url = db.Column(db.String(300))

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    shows = db.relationship(
        "Show",
        back_populates="movie",
        cascade="all, delete-orphan"
    )
    def __repr__(self):
        return f"<Movie {self.title}>"
