from datetime import datetime
from extensions import db

class Booking(db.Model):
    __tablename__ = "bookings"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    show_id = db.Column(db.Integer, db.ForeignKey("shows.id"))
    seats = db.Column(db.String(100))
    total_amount = db.Column(db.Float)
    status = db.Column(db.String(50), default="Booked")
    external_booking_url = db.Column(db.String(500))
    refund_status = db.Column(db.String(50), default="")
    refund_reference = db.Column(db.String(120), default="")
    booked_at = db.Column(db.DateTime, default=datetime.utcnow)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    show = db.relationship("Show", back_populates="bookings")
    payment = db.relationship(
        "Payment",
        back_populates="booking",
        cascade="all, delete-orphan",
        uselist=False
    )

class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("bookings.id"), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    amount = db.Column(db.Float)
    method = db.Column(db.String(50))
    status = db.Column(db.String(50), default="success")
    purpose = db.Column(db.String(50), default="booking")
    provider_reference = db.Column(db.String(120))
    receipt_number = db.Column(db.String(80), default="")
    failure_reason = db.Column(db.String(255), default="")
    refunded_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    booking = db.relationship("Booking", back_populates="payment")
