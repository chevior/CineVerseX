class BaseUser:

    def login(self):
        print("User Logged In")


class Customer(BaseUser):

    def book_ticket(self):
        print("Booking Ticket")


class Admin(BaseUser):

    def maintenance_mode(self):
        print("Maintenance Enabled")


class TheaterOwner(BaseUser):

    def add_show(self):
        print("Show Added")