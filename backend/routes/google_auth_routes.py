import json
import os
import secrets
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from flask import Blueprint, flash, redirect, request, session, url_for
from flask_login import login_user
from werkzeug.security import generate_password_hash

from extensions import db
from models.user import User
from services.activity_service import log_activity

google_auth_bp = Blueprint("google_auth_bp", __name__, url_prefix="/auth/google")


def google_redirect_uri():
    configured_uri = os.environ.get("GOOGLE_REDIRECT_URI", "").strip()
    if configured_uri:
        return configured_uri

    return url_for("google_auth_bp.google_callback", _external=True)


def google_oauth_config():
    return {
        "client_id": os.environ.get("GOOGLE_CLIENT_ID", "").strip(),
        "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET", "").strip(),
        "redirect_uri": google_redirect_uri(),
    }


def missing_google_config_message(config):
    missing = []

    if not config["client_id"]:
        missing.append("GOOGLE_CLIENT_ID")

    if not config["client_secret"]:
        missing.append("GOOGLE_CLIENT_SECRET")

    if not missing:
        return ""

    return f"Google Login is not configured yet. Missing: {', '.join(missing)}."


def post_google_token(code, config):
    data = urlencode({
        "code": code,
        "client_id": config["client_id"],
        "client_secret": config["client_secret"],
        "redirect_uri": config["redirect_uri"],
        "grant_type": "authorization_code",
    }).encode("utf-8")

    token_request = UrlRequest(
        "https://oauth2.googleapis.com/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    with urlopen(token_request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_google_profile(access_token):
    profile_request = UrlRequest(
        "https://www.googleapis.com/oauth2/v3/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    with urlopen(profile_request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def login_google_user(profile):
    email = (profile.get("email") or "").strip().lower()
    google_id = (profile.get("sub") or "").strip()
    name = (profile.get("name") or email.split("@")[0] or "Google User").strip()

    if not email or not google_id:
        raise ValueError("Google did not return a usable profile.")

    if profile.get("email_verified") is False:
        raise ValueError("Google email is not verified.")

    user = User.query.filter_by(google_id=google_id).first()
    if not user:
        user = User.query.filter_by(email=email).first()

    created = False
    if not user:
        user = User(
            name=name,
            email=email,
            google_id=google_id,
            password=generate_password_hash(secrets.token_urlsafe(32)),
        )
        db.session.add(user)
        db.session.flush()
        created = True
    else:
        user.google_id = user.google_id or google_id
        if not user.name:
            user.name = name

    db.session.commit()

    login_user(user)
    session["user_id"] = user.id
    session["user_name"] = user.name
    session["user_role"] = user.role

    if created:
        log_activity("New User Registration", f"{user.email} registered with Google.", user_id=user.id, notify=True)

    log_activity(
        "Admin Login" if user.role == "admin" else "User Login",
        f"{user.email} logged in with Google.",
        user_id=user.id,
        notify=user.role == "admin",
    )

    return user


@google_auth_bp.route("/login")
def google_login():
    config = google_oauth_config()
    missing_message = missing_google_config_message(config)

    if missing_message:
        flash(missing_message, "warning")
        return redirect(url_for("auth_bp.login"))

    state = secrets.token_urlsafe(24)
    session["google_oauth_state"] = state

    params = {
        "client_id": config["client_id"],
        "redirect_uri": config["redirect_uri"],
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
        "state": state,
    }
    return redirect(f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}")


@google_auth_bp.route("/callback")
def google_callback():
    if request.args.get("error"):
        flash("Google login was cancelled or denied.", "danger")
        return redirect(url_for("auth_bp.login"))

    code = request.args.get("code", "")
    state = request.args.get("state", "")
    expected_state = session.pop("google_oauth_state", "")

    if not code or not state or state != expected_state:
        flash("Google login could not be verified. Please try again.", "danger")
        return redirect(url_for("auth_bp.login"))

    config = google_oauth_config()
    missing_message = missing_google_config_message(config)

    if missing_message:
        flash(missing_message, "warning")
        return redirect(url_for("auth_bp.login"))

    try:
        token_data = post_google_token(code, config)
        access_token = token_data.get("access_token", "")
        if not access_token:
            raise ValueError("Google did not return an access token.")

        profile = fetch_google_profile(access_token)
        login_google_user(profile)
        flash("Logged in with Google successfully.", "success")
        return redirect(url_for("auth_bp.dashboard"))
    except (HTTPError, URLError, ValueError, json.JSONDecodeError) as error:
        flash(f"Google login failed: {error}", "danger")
        return redirect(url_for("auth_bp.login"))
