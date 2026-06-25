from extensions import db

class Theater(db.Model):
    __tablename__ = "theaters"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(200), nullable=False)

    city = db.Column(db.String(100), nullable=False)

    address = db.Column(db.Text)

    total_screens = db.Column(db.Integer, default=1)


class Screen(db.Model):
    __tablename__ = "screens"

    id = db.Column(db.Integer, primary_key=True)

    theater_id = db.Column(
        db.Integer,
        db.ForeignKey("theaters.id")
    )

    screen_name = db.Column(db.String(100))

    total_seats = db.Column(db.Integer)