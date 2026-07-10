import os
from base64 import b64encode
from io import BytesIO
from datetime import datetime, timedelta
from urllib.parse import quote_plus, urlencode
from uuid import uuid4

import qrcode
from flask import Blueprint, Response, flash, redirect, render_template, request, session, url_for

from auth.guards import login_required
from extensions import db
from models.booking import Booking, Payment
from models.user import User
from services.activity_service import log_activity

payment_bp = Blueprint("payment_bp", __name__, url_prefix="/payments")

PRO_PLAN_PRICE = 69.0
PRO_PLAN_DAYS = 30
UPI_PAYEE_NAME = "CineVerseX"


def env_file_value(key):
    env_paths = [
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env")),
    ]

    for env_path in env_paths:
        if not os.path.isfile(env_path):
            continue

        with open(env_path, "r", encoding="utf-8") as env_file:
            for line in env_file:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue

                name, value = line.split("=", 1)
                if name.strip() == key:
                    return value.strip().strip('"').strip("'")

    return ""


def configured_upi_id():
    return (
        os.environ.get("UPI_ID", "").strip()
        or env_file_value("UPI_ID")
    )


def upi_payment_enabled():
    return bool(configured_upi_id())


def upi_payment_url(amount=None, note=None):
    upi_id = configured_upi_id()

    if not upi_id:
        return ""

    params = {
        "pa": upi_id,
        "pn": UPI_PAYEE_NAME,
        "am": str(int(amount or PRO_PLAN_PRICE)),
        "cu": "INR",
        "tn": note or f"{UPI_PAYEE_NAME} Pro Plan",
    }
    return f"upi://pay?{urlencode(params, quote_via=quote_plus)}"


def upi_qr_data_uri(payment_url):
    qr_image = qrcode.make(payment_url)
    buffer = BytesIO()
    qr_image.save(buffer, format="PNG")
    encoded = b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def upi_url_for_payment(payment):
    note = f"{UPI_PAYEE_NAME} Pro"
    return upi_payment_url(payment.amount or PRO_PLAN_PRICE, note)


def current_subscription(user):
    plan = user.subscription_plan or "free"
    status = user.subscription_status or "active"

    if user.subscription_expires_at and user.subscription_expires_at < datetime.utcnow():
        plan = "free"
        status = "expired"

    return {
        "plan": plan,
        "status": status,
        "expires_at": user.subscription_expires_at,
        "is_pro": plan == "pro" and status == "active",
    }


@payment_bp.route("/pricing")
def pricing():
    user = None
    subscription = None

    if session.get("user_id"):
        user = db.session.get(User, session["user_id"])
        if user:
            subscription = current_subscription(user)

    return render_template(
        "pricing.html",
        user=user,
        subscription=subscription,
        pro_price=PRO_PLAN_PRICE,
        pro_days=PRO_PLAN_DAYS,
        upi_id=configured_upi_id(),
        upi_payment_enabled=upi_payment_enabled(),
    )


@payment_bp.route("/upi/pro")
@login_required
def upi_pro_payment():
    if not upi_payment_enabled():
        flash("UPI is not configured yet. Add UPI_ID in .env.", "warning")
        return redirect(url_for("payment_bp.pricing"))

    user = User.query.get_or_404(session["user_id"])
    reference = f"upi_{uuid4().hex[:12]}"
    payment_url = upi_payment_url(PRO_PLAN_PRICE, f"{UPI_PAYEE_NAME} Pro")
    payment = Payment(
        user_id=user.id,
        amount=PRO_PLAN_PRICE,
        method="UPI",
        status=f"pending:{reference}",
        purpose="subscription_pro",
        provider_reference=reference,
        created_at=datetime.utcnow(),
    )
    db.session.add(payment)
    db.session.commit()
    log_activity("Payment Success", f"UPI Pro payment page opened for {user.email}.", user_id=user.id)

    return render_template(
        "upi_payment.html",
        payment=payment,
        amount=PRO_PLAN_PRICE,
        days=PRO_PLAN_DAYS,
        open_payment_url=url_for("payment_bp.open_upi_payment", payment_id=payment.id),
        qr_data_uri=upi_qr_data_uri(payment_url),
    )


@payment_bp.route("/upi/open/<int:payment_id>")
@login_required
def open_upi_payment(payment_id):
    payment = Payment.query.get_or_404(payment_id)

    if payment.user_id != session["user_id"]:
        return "Access denied", 403

    if not upi_payment_enabled():
        flash("UPI is not configured yet. Add UPI_ID in .env.", "warning")
        return redirect(url_for("payment_bp.pricing"))

    return redirect(upi_url_for_payment(payment))


@payment_bp.route("/subscribe/free", methods=["POST"])
@login_required
def subscribe_free():
    user = User.query.get_or_404(session["user_id"])
    user.subscription_plan = "free"
    user.subscription_status = "active"
    user.subscription_started_at = datetime.utcnow()
    user.subscription_expires_at = None
    db.session.commit()

    log_activity("Subscription Updated", f"{user.email} switched to Free plan.", user_id=user.id)
    flash("You are now on the Free plan.", "success")
    return redirect(url_for("payment_bp.pricing"))


@payment_bp.route("/subscribe/pro", methods=["POST"])
@login_required
def subscribe_pro():
    user = User.query.get_or_404(session["user_id"])
    now = datetime.utcnow()
    reference = f"sub_{uuid4().hex[:14]}"
    method = "UPI" if upi_payment_enabled() else "Demo"
    status = "success" if method == "Demo" else f"pending:{reference}"

    payment = Payment(
        user_id=user.id,
        amount=PRO_PLAN_PRICE,
        method=method,
        status=status,
        purpose="subscription_pro",
        provider_reference=reference,
        created_at=now,
    )

    db.session.add(payment)

    if method == "Demo":
        user.subscription_plan = "pro"
        user.subscription_status = "active"
        user.subscription_started_at = now
        user.subscription_expires_at = now + timedelta(days=PRO_PLAN_DAYS)
        flash("Pro activated in demo mode. Add UPI_ID for live UPI payments.", "success")
        log_activity("Payment Success", f"Demo Pro subscription activated for {user.email}.", user_id=user.id, notify=True)
    else:
        user.subscription_status = "pending"
        flash("UPI payment initialized. Complete payment in your UPI app and keep the UPI reference.", "info")
        log_activity("Payment Success", f"UPI Pro payment initialized for {user.email}.", user_id=user.id)

    db.session.commit()
    return redirect(url_for("payment_bp.payment_history"))


@payment_bp.route("/history")
@login_required
def payment_history():
    payments = (
        Payment.query
        .outerjoin(Booking, Payment.booking_id == Booking.id)
        .filter((Booking.user_id == session["user_id"]) | (Payment.user_id == session["user_id"]))
        .order_by(Payment.id.desc())
        .all()
    )
    user = User.query.get_or_404(session["user_id"])

    return render_template(
        "payment_history.html",
        payments=payments,
        subscription=current_subscription(user),
    )


@payment_bp.route("/receipt/<int:payment_id>")
@login_required
def payment_receipt(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    if payment.user_id != session["user_id"] and session.get("user_role") != "admin":
        if not payment.booking or payment.booking.user_id != session["user_id"]:
            return "Access denied", 403

    lines = [
        "CineVerseX Payment Receipt",
        f"Receipt: {payment.receipt_number or payment.provider_reference or payment.id}",
        f"Payment ID: {payment.id}",
        f"Purpose: {payment.purpose or 'booking'}",
        f"Amount: Rs. {payment.amount}",
        f"Method: {payment.method}",
        f"Status: {payment.status}",
        f"Date: {payment.created_at.strftime('%Y-%m-%d %H:%M') if payment.created_at else '-'}",
        "",
        "GST Invoice",
        f"Taxable Value: Rs. {round(float(payment.amount or 0) / 1.18, 2)}",
        f"GST 18%: Rs. {round(float(payment.amount or 0) - (float(payment.amount or 0) / 1.18), 2)}",
        f"Invoice Total: Rs. {payment.amount}",
    ]
    return Response("\n".join(lines), mimetype="text/plain")


@payment_bp.route("/retry/<int:payment_id>", methods=["POST"])
@login_required
def retry_payment(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    if payment.user_id != session["user_id"] and (not payment.booking or payment.booking.user_id != session["user_id"]):
        return "Access denied", 403

    payment.status = "success"
    payment.failure_reason = ""
    payment.provider_reference = payment.provider_reference or f"retry_{uuid4().hex[:12]}"
    payment.receipt_number = payment.receipt_number or f"CX-{datetime.utcnow().strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}"
    db.session.commit()
    log_activity("Payment Retry Success", f"Payment #{payment.id} completed on retry.", user_id=session["user_id"])
    flash("Payment retry completed successfully.", "success")
    return redirect(url_for("payment_bp.payment_history"))


@payment_bp.route("/mark-failed/<int:payment_id>", methods=["POST"])
@login_required
def mark_payment_failed(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    if payment.user_id != session["user_id"] and (not payment.booking or payment.booking.user_id != session["user_id"]):
        return "Access denied", 403

    payment.status = "failed"
    payment.failure_reason = request.form.get("failure_reason", "Payment gateway declined the transaction.")
    db.session.commit()
    log_activity("Payment Failure", f"Payment #{payment.id} failed: {payment.failure_reason}", user_id=session["user_id"])
    flash("Payment marked failed. You can retry it from history.", "warning")
    return redirect(url_for("payment_bp.payment_history"))


@payment_bp.route("/refund/<int:payment_id>", methods=["POST"])
@login_required
def refund_payment(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    if session.get("user_role") != "admin":
        return "Access denied", 403

    payment.status = "refunded"
    payment.refunded_at = datetime.utcnow()
    if payment.booking:
        payment.booking.refund_status = "Completed"
        payment.booking.refund_reference = payment.booking.refund_reference or f"refund_{uuid4().hex[:12]}"
    db.session.commit()
    log_activity("Refund Completed", f"Payment #{payment.id} refunded.", notify=True)
    flash("Refund completed.", "success")
    return redirect(url_for("payment_bp.payment_history"))


@payment_bp.route("/upi/<int:booking_id>")
@login_required
def upi_checkout(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    if booking.user_id != session["user_id"]:
        return "Access denied", 403

    if not upi_payment_enabled():
        flash("UPI is not configured yet. Add UPI_ID in .env.", "warning")
        log_activity("Payment Failure", f"UPI not configured for booking #{booking.id}")
        return redirect(url_for("payment_bp.payment_history"))

    payment = Payment.query.filter_by(booking_id=booking.id).first()
    if not payment:
        payment = Payment(
            booking_id=booking.id,
            user_id=booking.user_id,
            amount=booking.total_amount,
            method="UPI",
            purpose="booking",
        )
        db.session.add(payment)

    payment.method = "UPI"
    payment.status = f"pending:{uuid4().hex[:12]}"
    payment.receipt_number = payment.receipt_number or f"CX-{datetime.utcnow().strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}"
    payment.created_at = payment.created_at or datetime.utcnow()
    db.session.commit()
    log_activity("Payment Success", f"UPI payment initialized for booking #{booking.id}")
    return render_template("payment_success.html", booking=booking, payment=payment)
