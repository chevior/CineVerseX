from datetime import datetime
from extensions import db

class Ticket(db.Model):
    __tablename__ = "tickets"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    movie_name = db.Column(db.String(100), nullable=False)
    theatre_name = db.Column(db.String(100), nullable=False)
    show_time = db.Column(db.String(50), nullable=False)
    seat_numbers = db.Column(db.String(100), nullable=False)
    total_amount = db.Column(db.Float, nullable=False)

    booking_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default="Booked")

    qr_code = db.Column(db.String(255))