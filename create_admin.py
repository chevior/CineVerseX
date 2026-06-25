import os
import sys

BASE_DIR = os.path.join(os.path.dirname(__file__), "backend")
sys.path.insert(0, BASE_DIR)

from app import app
from extensions import db
from models.user import User

with app.app_context():
    existing_user = User.query.filter_by(email="nchethan066@gmail.com").first()

    if existing_user:
        existing_user.role = "admin"
        existing_user.password = "admin123"
        db.session.commit()
        print("Existing user updated to admin")
    else:
        admin = User(
            name="Chethan",
            email="nchethan066@gmail.com",
            password="admin123",
            role="admin"
        )

        db.session.add(admin)
        db.session.commit()
        print("Admin created successfully")