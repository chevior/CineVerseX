import os
import sys
import bcrypt

BASE_DIR = os.path.join(os.path.dirname(__file__), "backend")
sys.path.insert(0, BASE_DIR)

from app import app
from extensions import db
from models.user import User

with app.app_context():
    hashed_password = bcrypt.hashpw(
        "admin123".encode(),
        bcrypt.gensalt()
    ).decode()

    existing_user = User.query.filter_by(
        email="nchethan066@gmail.com"
    ).first()

    if existing_user:
        existing_user.role = "admin"
        existing_user.password = hashed_password
        db.session.commit()
        print("Existing user updated to admin with hashed password")
    else:
        admin = User(
            name="Chethan",
            email="nchethan066@gmail.com",
            password=hashed_password,
            role="admin"
        )

        db.session.add(admin)
        db.session.commit()
        print("Admin created successfully with hashed password")