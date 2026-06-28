import secrets
import time
from collections import defaultdict, deque

from flask import abort, current_app, g, request, session


RATE_LIMITS = defaultdict(deque)


def configure_security(app):
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")
    app.config.setdefault("PERMANENT_SESSION_LIFETIME", 60 * 60 * 8)
    app.config["SESSION_COOKIE_SECURE"] = app.config.get("SESSION_COOKIE_SECURE", False)


def validate_password_strength(password):
    password = password or ""

    if len(password) < 8:
        return "Password must be at least 8 characters."

    if not any(char.isdigit() for char in password):
        return "Password must include at least one number."

    if not any(char.isalpha() for char in password):
        return "Password must include at least one letter."

    return ""


def ensure_csrf_token():
    session.setdefault("csrf_token", secrets.token_urlsafe(32))
    return session["csrf_token"]


def check_rate_limit():
    if request.endpoint == "static":
        return None

    window_seconds = int(current_app.config.get("RATE_LIMIT_WINDOW", 60))
    max_requests = int(current_app.config.get("RATE_LIMIT_REQUESTS", 180))
    key = request.headers.get("X-Forwarded-For", request.remote_addr or "local")
    now = time.time()
    bucket = RATE_LIMITS[key]

    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()

    if len(bucket) >= max_requests:
        abort(429)

    bucket.append(now)
    g.csrf_token = ensure_csrf_token()
    return None


def validate_csrf_request():
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None

    if request.endpoint and request.endpoint.startswith("api_bp."):
        return None

    expected = session.get("csrf_token")
    supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")

    if not expected or not supplied or supplied != expected:
        abort(400, description="Invalid CSRF token")

    return None


def apply_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self' https: data: blob: 'unsafe-inline' 'unsafe-eval'; frame-ancestors 'self';"
    )
    return response
