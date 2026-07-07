from flask import current_app, url_for
from flask_mail import Message

from extensions import mail
from models.setting import SystemSetting


def email_enabled():
    settings = SystemSetting.query.first()
    return bool(settings and settings.email_notifications_enabled)


def send_email(subject, recipients, body):
    if not recipients:
        return False

    if not email_enabled():
        current_app.logger.info("Email disabled. Subject=%s Recipients=%s", subject, recipients)
        return False

    try:
        mail.send(Message(subject=subject, recipients=recipients, body=body))
        return True
    except Exception as error:
        current_app.logger.warning("Email failed: %s", error)
        return False


def send_welcome_email(user):
    verify_url = url_for("auth_bp.verify_email", token=user.email_verification_token, _external=True)
    return send_email(
        "Welcome to CineVerseX",
        [user.email],
        (
            f"Hello {user.name},\n\n"
            "Welcome to CineVerseX. Verify your email to keep your account secure:\n"
            f"{verify_url}\n\n"
            "Thank you for joining CineVerseX."
        ),
    )


def send_password_reset_email(user):
    reset_url = url_for("auth_bp.reset_password_token", token=user.password_reset_token, _external=True)
    return send_email(
        "Reset your CineVerseX password",
        [user.email],
        (
            f"Hello {user.name},\n\n"
            "Use this secure link to reset your password. It expires soon:\n"
            f"{reset_url}\n\n"
            "If you did not request this, you can ignore this email."
        ),
    )


def send_ticket_email(user, booking, ticket):
    return send_email(
        "Your CineVerseX Ticket",
        [user.email],
        (
            f"Hello {user.name},\n\n"
            "Your ticket has been booked successfully.\n\n"
            f"Booking ID: {booking.id}\n"
            f"Movie: {ticket.movie_name}\n"
            f"Theatre: {ticket.theatre_name}\n"
            f"Show Time: {ticket.show_time}\n"
            f"Seats: {booking.seats}\n"
            f"Amount: Rs. {booking.total_amount}\n\n"
            "Thank you for booking with CineVerseX."
        ),
    )
