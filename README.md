# CineVerseX

CineVerseX is a full-stack Flask movie discovery and ticket-booking platform. It combines a public movie catalog, theater and show management, seat booking, payments, QR-style ticket flows, wishlist tools, user profiles, reports, and an admin dashboard in one portfolio-ready web app.

Live demo: https://cineversex.onrender.com

## Highlights

- Movie discovery with posters, details, search, wishlist, and BookMyShow/streaming discovery links
- User registration, login, Google OAuth, profile management, password reset, and email verification support
- Theater, screen, show, seat-selection, booking-history, payment, refund, and ticket-detail workflows
- Admin tools for movies, theaters, screens, shows, users, activity logs, review moderation, reports, and analytics
- Startup data initialization and schema backfills for local development
- Responsive Flask/Jinja interface with Bootstrap, custom CSS, and light/dark theme support

## Tech Stack

| Area | Technology |
| --- | --- |
| Backend | Flask |
| Database | SQLite with SQLAlchemy |
| Authentication | Flask-Login, Google OAuth |
| Email | Flask-Mail |
| UI | Jinja templates, Bootstrap, custom CSS |
| Reports/Tickets | CSV exports, QR code, PDF tooling |
| Deployment | Render/Gunicorn |

## Project Structure

```text
CineVerseX/
  backend/
    app.py
    config.py
    auth/
    data/
    models/
    routes/
    services/
    static/
    templates/
  scripts/
  artifacts/
  requirements.txt
  vercel.json
  README.md
```

## Local Setup

1. Clone the repository.

```bash
git clone https://github.com/chevior/CineVerseX.git
cd CineVerseX
```

2. Create and activate a virtual environment.

```bash
python -m venv venv
venv\Scripts\activate
```

For Linux or macOS:

```bash
source venv/bin/activate
```

3. Install dependencies.

```bash
pip install -r requirements.txt
```

4. Create a `.env` file in the project root.

```env
SECRET_KEY=change-me
DATABASE_URL=sqlite:///cineversex.db

GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://127.0.0.1:5000/auth/google/callback

MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=your_email@example.com
MAIL_PASSWORD=your_app_password
MAIL_DEFAULT_SENDER=your_email@example.com
```

5. Run the app.

```bash
python backend/app.py
```

Open http://127.0.0.1:5000.

## Default Admin

The local startup seed creates or refreshes a default admin user for development:

```text
Email: admin@example.com
Password: ChangeMe123!
```

Change these credentials before using the app beyond local development.

## Useful Routes

- `/` - home page
- `/movies` - movie catalog
- `/theaters` - theater listing
- `/shows` - show listing
- `/booking-history` - user bookings
- `/my-tickets` - user tickets
- `/admin` - admin dashboard
- `/health` - health check

## Deployment Notes

For Render or another production host:

- Set the required environment variables in the host dashboard.
- Use a strong `SECRET_KEY`.
- Configure Google OAuth redirect URLs for the deployed domain.
- Use a production database instead of the local SQLite file for real traffic.
- Start the app with Gunicorn, for example:

```bash
gunicorn backend.app:app
```

## Developer

Chethan N

GitHub: https://github.com/chevior

## License

This project is developed for educational and portfolio purposes.
