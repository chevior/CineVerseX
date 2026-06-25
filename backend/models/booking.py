from datetime import datetime
from extensions import db

class Booking(db.Model):
    __tablename__ = "bookings"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    show_id = db.Column(db.Integer, db.ForeignKey("shows.id"))
    seats = db.Column(db.String(100))
    total_amount = db.Column(db.Float)
    status = db.Column(db.String(50), default="confirmed")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("bookings.id"))
    amount = db.Column(db.Float)
    method = db.Column(db.String(50))
    status = db.Column(db.String(50), default="success")