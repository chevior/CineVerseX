from datetime import datetime

from extensions import db
from models.user import User


class Review(db.Model):
    __tablename__ = "reviews"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    movie_id = db.Column(db.Integer, db.ForeignKey("movies.id"), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, default="")
    likes = db.Column(db.Integer, default=0)
    report_count = db.Column(db.Integer, default=0)
    status = db.Column(db.String(30), default="approved")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    user = db.relationship("User", backref="reviews")
    movie = db.relationship("Movie", backref="reviews")

    __table_args__ = (
        db.UniqueConstraint("user_id", "movie_id", name="unique_user_movie_review"),
    )
