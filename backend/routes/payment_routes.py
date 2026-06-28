import os
from datetime import datetime, timedelta
from uuid import uuid4

from flask import Blueprint, flash, redirect, render_template, session, url_for

from auth.guards import login_required
from extensions import db
from models.booking import Booking, Payment
from models.user import User
from services.activity_service import log_activity

payment_bp = Blueprint("payment_bp", __name__, url_prefix="/payments")

PRO_PLAN_PRICE = 199.0
PRO_PLAN_DAYS = 30


def razorpay_configured():
    return bool(os.environ.get("RAZORPAY_KEY_ID") and os.environ.get("RAZORPAY_KEY_SECRET"))


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
        razorpay_enabled=razorpay_configured(),
    )


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
    method = "Razorpay" if razorpay_configured() else "Demo"
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
        flash("Pro activated in demo mode. Add Razorpay keys on Render for live payments.", "success")
        log_activity("Payment Success", f"Demo Pro subscription activated for {user.email}.", user_id=user.id, notify=True)
    else:
        user.subscription_status = "pending"
        flash("Razorpay checkout initialized. Complete payment verification to activate Pro.", "info")
        log_activity("Payment Success", f"Razorpay Pro checkout initialized for {user.email}.", user_id=user.id)

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


@payment_bp.route("/razorpay/<int:booking_id>")
@login_required
def razorpay_checkout(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    if booking.user_id != session["user_id"]:
        return "Access denied", 403

    if not razorpay_configured():
        flash("Razorpay is not configured yet. Add RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET.", "warning")
        log_activity("Payment Failure", f"Razorpay not configured for booking #{booking.id}")
        return redirect(url_for("payment_bp.payment_history"))

    payment = Payment.query.filter_by(booking_id=booking.id).first()
    if not payment:
        payment = Payment(
            booking_id=booking.id,
            user_id=booking.user_id,
            amount=booking.total_amount,
            method="Razorpay",
            purpose="booking",
        )
        db.session.add(payment)

    payment.method = "Razorpay"
    payment.status = f"pending:{uuid4().hex[:12]}"
    payment.created_at = payment.created_at or datetime.utcnow()
    db.session.commit()
    log_activity("Payment Success", f"Razorpay checkout initialized for booking #{booking.id}")
    return render_template("payment_success.html", booking=booking, payment=payment)
