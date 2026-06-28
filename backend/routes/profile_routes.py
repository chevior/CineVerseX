import os
from uuid import uuid4

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename

from auth.guards import login_required
from extensions import db
from models.booking import Booking
from models.ticket import Ticket
from models.user import User
from routes.auth_routes import password_matches
from services.security_service import validate_password_strength

profile_bp = Blueprint("profile_bp", __name__)

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


def allowed_profile_image(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


@profile_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user = User.query.get_or_404(session["user_id"])

    if request.method == "POST":
        user.name = request.form.get("name", user.name).strip() or user.name
        new_email = request.form.get("email", user.email).strip().lower()

        existing_email = User.query.filter(User.email == new_email, User.id != user.id).first()
        if existing_email:
            flash("That email is already used by another account.", "danger")
            return redirect(url_for("profile_bp.profile"))

        user.email = new_email

        image = request.files.get("profile_picture")
        if image and image.filename and allowed_profile_image(image.filename):
            filename = f"{uuid4().hex}.{secure_filename(image.filename).rsplit('.', 1)[1].lower()}"
            folder = os.path.join(current_app.root_path, "static", "profiles")
            os.makedirs(folder, exist_ok=True)
            image.save(os.path.join(folder, filename))
            user.profile_picture = f"profiles/{filename}"

        db.session.commit()
        session["user_name"] = user.name
        flash("Profile updated.", "success")
        return redirect(url_for("profile_bp.profile"))

    bookings = Booking.query.filter_by(user_id=user.id).all()
    tickets = Ticket.query.filter_by(user_id=user.id).all()
    total_spent = sum(ticket.total_amount or 0 for ticket in tickets if ticket.status != "Cancelled")

    return render_template(
        "profile.html",
        user=user,
        total_bookings=len(bookings),
        total_tickets=len(tickets),
        total_spent=round(total_spent, 2),
    )


@profile_bp.route("/profile/change-password", methods=["POST"])
@login_required
def profile_change_password():
    user = User.query.get_or_404(session["user_id"])
    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not password_matches(user, current_password):
        flash("Current password is incorrect.", "danger")
        return redirect(url_for("profile_bp.profile"))

    if new_password != confirm_password:
        flash("New passwords do not match.", "danger")
        return redirect(url_for("profile_bp.profile"))

    strength_error = validate_password_strength(new_password)
    if strength_error:
        flash(strength_error, "danger")
        return redirect(url_for("profile_bp.profile"))

    user.password = generate_password_hash(new_password)
    db.session.commit()
    flash("Password changed successfully.", "success")
    return redirect(url_for("profile_bp.profile"))
