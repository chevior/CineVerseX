from extensions import db

class SystemSetting(db.Model):
    __tablename__ = "system_settings"

    id = db.Column(db.Integer, primary_key=True)

    site_name = db.Column(db.String(100), default="CineVerseX")
    support_email = db.Column(db.String(120), default="support@cineversex.com")
    support_discord_link = db.Column(db.String(255), default="")
    support_phone = db.Column(db.String(20), default="")

    maintenance_mode = db.Column(db.Boolean, default=False)
    booking_enabled = db.Column(db.Boolean, default=True)
    registration_enabled = db.Column(db.Boolean, default=True)

    max_seats_per_booking = db.Column(db.Integer, default=6)
    cancel_hours_before_show = db.Column(db.Integer, default=2)

    booking_fee = db.Column(db.Float, default=0.0)
    tax_percentage = db.Column(db.Float, default=0.0)

    payment_gateway_enabled = db.Column(db.Boolean, default=False)
    email_notifications_enabled = db.Column(db.Boolean, default=False)
