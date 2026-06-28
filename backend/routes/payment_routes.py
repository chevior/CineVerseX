import os
from uuid import uuid4

from flask import Blueprint, flash, redirect, render_template, session, url_for

from auth.guards import login_required
from extensions import db
from models.booking import Booking, Payment
from services.activity_service import log_activity

payment_bp = Blueprint("payment_bp", __name__, url_prefix="/payments")


@payment_bp.route("/history")
@login_required
def payment_history():
    payments = (
        Payment.query
        .join(Booking, Payment.booking_id == Booking.id)
        .filter(Booking.user_id == session["user_id"])
        .order_by(Payment.id.desc())
        .all()
    )
    return render_template("payment_history.html", payments=payments)


@payment_bp.route("/razorpay/<int:booking_id>")
@login_required
def razorpay_checkout(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    if booking.user_id != session["user_id"]:
        return "Access denied", 403

    if not os.environ.get("RAZORPAY_KEY_ID") or not os.environ.get("RAZORPAY_KEY_SECRET"):
        flash("Razorpay is not configured yet. Add RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET.", "warning")
        log_activity("Payment Failure", f"Razorpay not configured for booking #{booking.id}")
        return redirect(url_for("payment_bp.payment_history"))

    payment = Payment.query.filter_by(booking_id=booking.id).first()
    if not payment:
        payment = Payment(booking_id=booking.id, amount=booking.total_amount, method="Razorpay")
        db.session.add(payment)

    payment.method = "Razorpay"
    payment.status = f"pending:{uuid4().hex[:12]}"
    db.session.commit()
    log_activity("Payment Success", f"Razorpay checkout initialized for booking #{booking.id}")
    return render_template("payment_success.html", booking=booking, payment=payment)
