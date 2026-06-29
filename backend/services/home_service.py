import html
import os
import sqlite3
from datetime import datetime

from flask import current_app
from sqlalchemy import func

from extensions import db
from models.booking import Booking
from models.movie import Movie
from models.show import Show
from models.theater import Theater
from services.booking_metrics_service import active_engagement_filter


def local_imdb_db_path():
    configured_path = current_app.config.get("IMDB_DB_PATH", "").strip()

    if configured_path:
        return os.path.abspath(configured_path)

    packaged_seed_path = os.path.abspath(
        os.path.join(current_app.root_path, "data", "imdb_seed.db")
    )

    if os.path.isfile(packaged_seed_path):
        return packaged_seed_path

    return os.path.abspath(os.path.join(current_app.root_path, "..", "cineversex.db"))


def local_imdb_movie_count():
    cache_key = "LOCAL_IMDB_MOVIE_COUNT"

    if cache_key in current_app.config:
        return current_app.config[cache_key]

    imdb_path = local_imdb_db_path()

    if not os.path.isfile(imdb_path):
        current_app.config[cache_key] = 0
        return 0

    try:
        connection = sqlite3.connect(f"file:{imdb_path}?mode=ro", uri=True)
        count = connection.execute(
            """
            SELECT COUNT(*)
            FROM imdb_titles
            WHERE titleType = 'movie'
            AND isAdult = 0
            """
        ).fetchone()[0]
        connection.close()
    except Exception:
        count = 0

    current_app.config[cache_key] = count
    return count


def build_home_context():
    trending_movie = (
        db.session.query(
            Movie,
            func.count(Booking.id).label("booking_count")
        )
        .join(Show, Show.movie_id == Movie.id)
        .join(Booking, Booking.show_id == Show.id)
        .filter(active_engagement_filter())
        .group_by(Movie.id)
        .order_by(func.count(Booking.id).desc())
        .first()
    )

    if not trending_movie:
        fallback_movie = Movie.query.order_by(Movie.rating.desc()).first()
        if fallback_movie:
            trending_movie = (fallback_movie, 0)

    today_key = datetime.utcnow().strftime("%Y-%m-%d")
    poster_first = Movie.poster_url.isnot(None).desc(), (Movie.poster_url != "").desc()
    homepage_movies = Movie.query.filter(
        Movie.data_source.in_(("tmdb", "imdbapi", "curated")),
        Movie.poster_url.isnot(None),
        Movie.poster_url != ""
    )
    hero_movies = homepage_movies.order_by(
        *poster_first,
        Movie.rating.desc(),
        Movie.title.asc()
    ).limit(5).all()
    featured_movies = homepage_movies.filter(
        Movie.release_date >= today_key
    ).order_by(
        *poster_first,
        Movie.release_date.asc(),
        Movie.rating.desc()
    ).limit(10).all()
    stream_movies = homepage_movies.order_by(
        *poster_first,
        Movie.rating.desc(),
        Movie.title.asc()
    ).offset(10).limit(10).all()
    top_rated_movies = homepage_movies.filter(
        Movie.data_source == "curated",
        Movie.release_date >= today_key
    ).order_by(
        *poster_first,
        Movie.release_date.asc(),
        Movie.title.asc()
    ).offset(5).limit(10).all()

    catalog_movie_count = Movie.query.filter(
        Movie.data_source.in_(("tmdb", "imdbapi", "curated"))
    ).count()
    catalog_rows = Movie.query.filter(
        Movie.data_source.in_(("tmdb", "imdbapi", "curated"))
    ).with_entities(Movie.genre, Movie.language).all()
    genre_count = len({
        item.strip()
        for row in catalog_rows
        for item in (row.genre or "").split(",")
        if item.strip()
    })
    language_count = len({
        item.strip()
        for row in catalog_rows
        for item in (row.language or "").split(",")
        if item.strip()
    })
    theater_count = Theater.query.filter(Theater.name != "BookMyShow").count()
    release_count = Show.query.join(Movie).filter(
        Movie.data_source.in_(("tmdb", "imdbapi", "curated")),
        Show.show_time >= today_key
    ).count()

    return {
        "trending_movie": trending_movie,
        "hero_movies": hero_movies,
        "featured_movies": featured_movies,
        "stream_movies": stream_movies,
        "top_rated_movies": top_rated_movies,
        "movie_count": local_imdb_movie_count() or catalog_movie_count,
        "catalog_movie_count": catalog_movie_count,
        "genre_count": genre_count,
        "language_count": language_count,
        "theater_count": theater_count,
        "release_count": release_count,
    }


def generated_movie_poster_svg(movie):
    title = html.escape(movie.title or "CineVerse X")
    genre = html.escape((movie.genre or "Upcoming Release").replace(",", " / "))
    release = html.escape(movie.release_date or "Coming Soon")
    language = html.escape(movie.language or "All Languages")
    initial = html.escape((movie.title or "C")[:1].upper())

    palette = [
        ("#101820", "#f2aa4c", "#29a19c"),
        ("#171321", "#ff4f79", "#6ee7b7"),
        ("#111827", "#facc15", "#38bdf8"),
        ("#1a120b", "#eab308", "#ef4444"),
        ("#0f172a", "#a78bfa", "#fb7185"),
        ("#132a13", "#fef08a", "#22c55e"),
    ]
    bg, accent, secondary = palette[movie.id % len(palette)]

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="640" height="960" viewBox="0 0 640 960">
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{bg}"/>
    <stop offset="1" stop-color="#050505"/>
  </linearGradient>
  <radialGradient id="glow" cx="35%" cy="20%" r="70%">
    <stop offset="0" stop-color="{accent}" stop-opacity="0.55"/>
    <stop offset="1" stop-color="{accent}" stop-opacity="0"/>
  </radialGradient>
</defs>
<rect width="640" height="960" fill="url(#bg)"/>
<rect width="640" height="960" fill="url(#glow)"/>
<circle cx="520" cy="170" r="170" fill="{secondary}" opacity="0.16"/>
<circle cx="105" cy="785" r="190" fill="{accent}" opacity="0.14"/>
<path d="M70 122 C190 68 335 70 485 122" fill="none" stroke="{accent}" stroke-width="4" opacity="0.8"/>
<text x="72" y="155" fill="{accent}" font-family="Arial, Helvetica, sans-serif" font-size="28" font-weight="700" letter-spacing="3">CINEVERSE X</text>
<text x="320" y="422" text-anchor="middle" fill="#ffffff" font-family="Arial, Helvetica, sans-serif" font-size="176" font-weight="900" opacity="0.22">{initial}</text>
<foreignObject x="62" y="490" width="516" height="210">
  <div xmlns="http://www.w3.org/1999/xhtml" style="font-family:Arial, Helvetica, sans-serif;color:#fff;font-size:48px;font-weight:900;line-height:1.04;text-transform:uppercase;word-break:break-word;">{title}</div>
</foreignObject>
<text x="64" y="735" fill="{accent}" font-family="Arial, Helvetica, sans-serif" font-size="26" font-weight="700">{release}</text>
<foreignObject x="64" y="765" width="512" height="70">
  <div xmlns="http://www.w3.org/1999/xhtml" style="font-family:Arial, Helvetica, sans-serif;color:#e5e7eb;font-size:24px;line-height:1.25;">{genre}</div>
</foreignObject>
<text x="64" y="872" fill="#ffffff" font-family="Arial, Helvetica, sans-serif" font-size="22" opacity="0.78">{language}</text>
<rect x="64" y="896" width="512" height="2" fill="{accent}" opacity="0.65"/>
</svg>"""
