from extensions import db

class Show(db.Model):
    __tablename__ = "shows"

    id = db.Column(db.Integer, primary_key=True)

    movie_id = db.Column(db.Integer, db.ForeignKey("movies.id"))
    theater_id = db.Column(db.Integer, db.ForeignKey("theaters.id"))
    screen_id = db.Column(db.Integer, db.ForeignKey("screens.id"))

    show_time = db.Column(db.String(100))
    price = db.Column(db.Float)