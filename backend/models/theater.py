from extensions import db

class Theater(db.Model):
    __tablename__ = "theaters"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(200), nullable=False)

    city = db.Column(db.String(100), nullable=False)

    address = db.Column(db.Text)

    total_screens = db.Column(db.Integer, default=1)

    amenities = db.Column(db.Text, default="")

    parking_info = db.Column(db.String(255), default="")

    food_available = db.Column(db.Boolean, default=True)

    map_url = db.Column(db.String(500), default="")

    screens = db.relationship(
        "Screen",
        back_populates="theater",
        cascade="all, delete-orphan"
    )

    shows = db.relationship(
        "Show",
        back_populates="theater",
        cascade="all, delete-orphan"
    )


class Screen(db.Model):
    __tablename__ = "screens"

    id = db.Column(db.Integer, primary_key=True)

    theater_id = db.Column(
        db.Integer,
        db.ForeignKey("theaters.id")
    )

    screen_name = db.Column(db.String(100))

    total_seats = db.Column(db.Integer)

    vip_seats = db.Column(db.Integer, default=0)

    premium_seats = db.Column(db.Integer, default=0)

    standard_seats = db.Column(db.Integer, default=0)

    couple_seats = db.Column(db.Integer, default=0)

    wheelchair_seats = db.Column(db.Integer, default=0)

    theater = db.relationship("Theater", back_populates="screens")
    shows = db.relationship(
        "Show",
        back_populates="screen",
        cascade="all, delete-orphan"
    )
