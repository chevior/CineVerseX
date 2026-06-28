from extensions import db
from datetime import datetime
from flask_login import UserMixin

class User(UserMixin, db.Model):

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100), nullable=False)

    email = db.Column(db.String(120), unique=True, nullable=False)

    password = db.Column(db.String(255), nullable=False)

    role = db.Column(db.String(50), default="customer")

    google_id = db.Column(db.String(120), unique=True)

    profile_picture = db.Column(db.String(255), default="")

    subscription_plan = db.Column(db.String(30), default="free")

    subscription_status = db.Column(db.String(30), default="active")

    subscription_started_at = db.Column(db.DateTime)

    subscription_expires_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
