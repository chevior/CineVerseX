from datetime import datetime, timedelta
import secrets

from flask import Blueprint, flash, render_template, request, redirect, url_for, session
import bcrypt
from flask_login import login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from auth.guards import login_required
from extensions import db
from models.setting import SystemSetting
from models.user import User
from services.activity_service import log_activity
from services.email_service import send_password_reset_email, send_welcome_email
from services.security_service import validate_password_strength

auth_bp = Blueprint("auth_bp", __name__)


def password_matches(user, password):
    try:
        if check_password_hash(user.password, password):
            return True
    except ValueError:
        pass

    try:
        return bcrypt.checkpw(password.encode(), user.password.encode())
    except ValueError:
        return False


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    settings = SystemSetting.query.first()
    if settings and not settings.registration_enabled:
        flash("New registration is currently disabled.", "warning")
        return redirect(url_for("auth_bp.login"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("auth_bp.register"))

        strength_error = validate_password_strength(password)
        if strength_error:
            flash(strength_error, "danger")
            return redirect(url_for("auth_bp.register"))

        if User.query.filter_by(email=email).first():
            flash("An account already exists for that email.", "danger")
            return redirect(url_for("auth_bp.login"))

        user = User(
            name=name,
            email=email,
            password=generate_password_hash(password),
            email_verified=False,
            email_verification_token=secrets.token_urlsafe(32),
        )
        db.session.add(user)
        db.session.commit()

        sent = send_welcome_email(user)
        log_activity("New User Registration", f"{user.email} registered.", user_id=user.id, notify=True)
        flash(
            "Account created. Check your email to verify it." if sent else
            "Account created. Email sending is disabled, so you can verify from the account link later.",
            "success"
        )
        return redirect(url_for("auth_bp.login"))

    return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()

        if user and password_matches(user, password):
            remember = "remember" in request.form
            login_user(user, remember=remember)
            user.remember_login = remember
            session["user_id"] = user.id
            session["user_name"] = user.name
            session["user_role"] = user.role
            db.session.commit()
            log_activity("User Login", f"{user.email} logged in.", user_id=user.id)
            flash("Welcome back.", "success")

            if user.role == "admin":
                return redirect(url_for("admin_bp.admin_dashboard"))

            return redirect(url_for("auth_bp.dashboard"))

        flash("Invalid email or password.", "danger")
        return redirect(url_for("auth_bp.login"))

    return render_template("login.html")


@auth_bp.route("/dashboard")
@login_required
def dashboard():
    return render_template(
        "dashboard.html",
        name=session["user_name"],
        role=session["user_role"]
    )


@auth_bp.route("/logout")
def logout():
    logout_user()
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth_bp.login"))


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()

        if user:
            user.password_reset_token = secrets.token_urlsafe(32)
            user.password_reset_expires_at = datetime.utcnow() + timedelta(hours=1)
            db.session.commit()
            send_password_reset_email(user)
            log_activity("Password Reset Requested", f"{user.email} requested a reset.", user_id=user.id)

        flash("If that email exists, a reset link has been sent.", "info")
        return redirect(url_for("auth_bp.login"))

    return render_template("reset_password.html", token=None)


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password_token(token):
    user = User.query.filter_by(password_reset_token=token).first_or_404()

    if not user.password_reset_expires_at or user.password_reset_expires_at < datetime.utcnow():
        flash("This reset link has expired. Request a new one.", "danger")
        return redirect(url_for("auth_bp.reset_password"))

    if request.method == "POST":
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if new_password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("auth_bp.reset_password_token", token=token))

        strength_error = validate_password_strength(new_password)
        if strength_error:
            flash(strength_error, "danger")
            return redirect(url_for("auth_bp.reset_password_token", token=token))

        user.password = generate_password_hash(new_password)
        user.password_reset_token = ""
        user.password_reset_expires_at = None
        db.session.commit()
        log_activity("Password Change", f"{user.email} reset password.", user_id=user.id)

        flash("Password reset. You can log in with the new password.", "success")
        return redirect(url_for("auth_bp.login"))

    return render_template("reset_password.html", token=token)


@auth_bp.route("/verify-email/<token>")
def verify_email(token):
    user = User.query.filter_by(email_verification_token=token).first_or_404()
    user.email_verified = True
    user.email_verification_token = ""
    db.session.commit()
    log_activity("Email Verified", f"{user.email} verified their email.", user_id=user.id)
    flash("Email verified successfully.", "success")
    return redirect(url_for("auth_bp.login"))


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    user = User.query.get_or_404(session["user_id"])

    if request.method == "POST":
        current_password = request.form["current_password"]
        new_password = request.form["new_password"]
        confirm_password = request.form["confirm_password"]

        if not password_matches(user, current_password):
            flash("Current password is incorrect.", "danger")
            return redirect(url_for("auth_bp.change_password"))

        if new_password != confirm_password:
            flash("New passwords do not match.", "danger")
            return redirect(url_for("auth_bp.change_password"))

        strength_error = validate_password_strength(new_password)
        if strength_error:
            flash(strength_error, "danger")
            return redirect(url_for("auth_bp.change_password"))

        user.password = generate_password_hash(new_password)
        db.session.commit()
        log_activity("Password Change", f"{user.email} changed password.", user_id=user.id)

        flash("Password changed successfully.", "success")
        return redirect(url_for("auth_bp.dashboard"))

    return render_template("change_password.html")
