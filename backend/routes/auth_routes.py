from flask import Blueprint, render_template, request, redirect, url_for, session
import bcrypt

from extensions import db
from models.user import User

auth_bp = Blueprint("auth_bp", __name__)

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        if User.query.filter_by(email=email).first():
            return "User already exists"

        hashed_password = bcrypt.hashpw(
            password.encode(),
            bcrypt.gensalt()
        ).decode()

        user = User(
            name=name,
            email=email,
            password=hashed_password
        )

        db.session.add(user)
        db.session.commit()

        return redirect(url_for("auth_bp.login"))

    return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        user = User.query.filter_by(email=email).first()

        if not user:
            return "User not found"

        if bcrypt.checkpw(password.encode(), user.password.encode()):
            session["user_id"] = user.id
            session["user_name"] = user.name
            session["user_role"] = user.role

            return redirect(url_for("auth_bp.dashboard"))

        return "Incorrect password"

    return render_template("login.html")


@auth_bp.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("auth_bp.login"))

    return render_template(
        "dashboard.html",
        name=session["user_name"],
        role=session["user_role"]
    )


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth_bp.login"))


@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        new_password = request.form["new_password"]

        user = User.query.filter_by(email=email).first()

        if not user:
            return "User not found"

        hashed_password = bcrypt.hashpw(
            new_password.encode("utf-8"),
            bcrypt.gensalt()
        ).decode("utf-8")

        user.password = hashed_password
        db.session.commit()

        if user.role == "admin":
            return redirect(url_for("admin_bp.admin_dashboard"))
        return redirect(url_for("auth_bp.dashboard"))

    return render_template("reset_password.html")
