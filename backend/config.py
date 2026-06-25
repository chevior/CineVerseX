class Config:

    SECRET_KEY = "cineversex_secret"

    SQLALCHEMY_DATABASE_URI = (
        "mysql+pymysql://root:chethan@localhost/cineversex"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False