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

    genre = db.Column(
        db.String(100)
    )

    release_date = db.Column(
        db.String(50)
    )

    rating = db.Column(
        db.Float,
        default=0
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    def __repr__(self):
        return f"<Movie {self.title}>"