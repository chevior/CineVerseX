# CineVerseX

## About

CineVerseX is a movie ticket booking and movie information web application built using Flask. Users can explore movies, view theaters, check upcoming releases, save movies to their wishlist, and access movie details. Administrators can manage movies, theaters, shows, and users through the admin panel.

## Features

* User registration and login
* Google Sign-In
* Browse and search movies
* Movie details with posters
* Upcoming movies
* Theater listing
* Wishlist
* Admin dashboard
* Manage movies, theaters, and shows
* CSV report export
* Light and Dark mode

## Technologies Used

* Python
* Flask
* SQLAlchemy
* SQLite
* HTML
* CSS
* Bootstrap
* JavaScript

## Project Structure

```text
CineVerseX/
│
├── backend/
│   ├── app.py
│   ├── models/
│   ├── routes/
│   ├── services/
│   ├── templates/
│   ├── static/
│   └── data/
│
├── scripts/
├── requirements.txt
└── README.md
```

## Installation

Create a virtual environment:

```bash
python -m venv venv
```

Activate the virtual environment:

```bash
venv\Scripts\activate
```

Install the required packages:

```bash
pip install -r requirements.txt
```

Run the application:

```bash
python backend\app.py
```

Open your browser:

```
http://127.0.0.1:5000
```

## Environment Variables

Create a `.env` file and add:

```text
SECRET_KEY=your-secret-key
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=http://127.0.0.1:5000/auth/google/callback
```

## Deployment

For Render deployment, set the same environment variables in the Render dashboard and update the Google OAuth redirect URI with your Render URL.

## Developer

Developed by **Chethan N**.
