import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "cineversex_secret_2026")
    IMDB_DB_PATH = os.environ.get("IMDB_DB_PATH", "")

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "sqlite:///cineversex.db"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False
