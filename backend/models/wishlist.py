from datetime import datetime

from extensions import db


class WishlistItem(db.Model):
    __tablename__ = "wishlist_items"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    movie_id = db.Column(db.Integer, db.ForeignKey("movies.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="wishlist_items")
    movie = db.relationship("Movie", backref="wishlist_items")

    __table_args__ = (
        db.UniqueConstraint("user_id", "movie_id", name="uq_wishlist_user_movie"),
    )
