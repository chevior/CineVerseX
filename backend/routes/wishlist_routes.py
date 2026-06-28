from flask import Blueprint, flash, redirect, render_template, session, url_for

from auth.guards import login_required
from extensions import db
from models.movie import Movie
from models.wishlist import WishlistItem

wishlist_bp = Blueprint("wishlist_bp", __name__)


@wishlist_bp.route("/wishlist")
@login_required
def wishlist():
    items = WishlistItem.query.filter_by(user_id=session["user_id"]).order_by(WishlistItem.created_at.desc()).all()
    return render_template("wishlist.html", items=items)


@wishlist_bp.route("/wishlist/add/<int:movie_id>", methods=["POST", "GET"])
@login_required
def add_to_wishlist(movie_id):
    Movie.query.get_or_404(movie_id)
    existing = WishlistItem.query.filter_by(user_id=session["user_id"], movie_id=movie_id).first()

    if not existing:
        db.session.add(WishlistItem(user_id=session["user_id"], movie_id=movie_id))
        db.session.commit()
        flash("Movie added to wishlist.", "success")

    return redirect(url_for("wishlist_bp.wishlist"))


@wishlist_bp.route("/wishlist/remove/<int:movie_id>", methods=["POST", "GET"])
@login_required
def remove_from_wishlist(movie_id):
    item = WishlistItem.query.filter_by(user_id=session["user_id"], movie_id=movie_id).first()

    if item:
        db.session.delete(item)
        db.session.commit()
        flash("Movie removed from wishlist.", "info")

    return redirect(url_for("wishlist_bp.wishlist"))
