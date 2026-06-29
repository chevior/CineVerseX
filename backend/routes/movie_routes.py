import os
import json
import sqlite3
from datetime import datetime
from html import escape
from urllib.parse import parse_qs, quote_plus, urlencode, urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from flask import Blueprint, Response, flash, render_template, request, current_app, redirect, url_for
from flask_login import current_user
from sqlalchemy import func, or_
from werkzeug.utils import secure_filename

from auth.guards import admin_required, login_required
from extensions import db
from models.movie import Movie
from models.review import Review
from models.show import Show
from models.theater import Theater
from services.activity_service import log_activity
from services.catalog_data import BOOKMYSHOW_HOME_URL, BOOKMYSHOW_MOVIE_PAGES

movie_bp = Blueprint("movie_bp", __name__)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
GENRES = [
    "Action",
    "Adventure",
    "Biography",
    "Comedy",
    "Crime",
    "Documentary",
    "Drama",
    "Family",
    "Fantasy",
    "History",
    "Music",
    "Mystery",
    "Romance",
    "Thriller",
    "Horror",
    "Animation",
    "Sci-Fi",
    "War",
    "Western",
]


def pagination_window(current_page, total_pages, radius=2):
    if total_pages <= 1:
        return []

    current_page = max(1, min(current_page, total_pages))
    pages = {1, total_pages}

    for page_number in range(current_page - radius, current_page + radius + 1):
        if 1 <= page_number <= total_pages:
            pages.add(page_number)

    ordered_pages = sorted(pages)
    window = []
    previous = None

    for page_number in ordered_pages:
        if previous is not None and page_number - previous > 1:
            window.append(None)

        window.append(page_number)
        previous = page_number

    return window


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def imdb_db_path():
    configured_path = current_app.config.get("IMDB_DB_PATH", "").strip()

    if configured_path:
        return os.path.abspath(configured_path)

    default_path = os.path.abspath(
        os.path.join(current_app.root_path, "..", "cineversex.db")
    )

    deploy_disk_path = os.path.abspath("/var/data/cineversex.db")

    if os.path.isfile(deploy_disk_path):
        return deploy_disk_path

    packaged_seed_path = os.path.abspath(
        os.path.join(current_app.root_path, "data", "imdb_seed.db")
    )

    if os.path.isfile(packaged_seed_path):
        return packaged_seed_path

    return default_path


def imdb_db_available():
    return os.path.isfile(imdb_db_path())


def imdb_database_label():
    if not imdb_db_available():
        return "IMDb database not connected"

    size_gb = os.path.getsize(imdb_db_path()) / (1024 ** 3)
    return f"Local IMDb database ({size_gb:.1f} GB)"


def normalize_title_key(title):
    normalized = " ".join((title or "").strip().lower().replace("-", " ").split())
    return normalized.replace(" :", ":")


def bookmyshow_search_url(title):
    title = (title or "").strip()

    if not title:
        return BOOKMYSHOW_HOME_URL

    return BOOKMYSHOW_MOVIE_PAGES.get(
        normalize_title_key(title),
        f"{BOOKMYSHOW_HOME_URL}search?q={quote_plus(title)}"
    )


def justwatch_search_url(title):
    return f"https://www.justwatch.com/in/search?q={quote_plus(title or '')}"


def tmdb_is_configured():
    return bool(
        os.environ.get("TMDB_BEARER_TOKEN", "").strip()
        or os.environ.get("TMDB_API_KEY", "").strip()
    )


def fetch_tmdb_json(path, params=None):
    params = params or {}
    api_key = os.environ.get("TMDB_API_KEY", "").strip()
    bearer_token = os.environ.get("TMDB_BEARER_TOKEN", "").strip()
    headers = {"accept": "application/json"}

    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    elif api_key:
        params["api_key"] = api_key

    api_request = Request(
        f"{TMDB_BASE_URL}{path}?{urlencode(params)}",
        headers=headers
    )

    with urlopen(api_request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8"))


def imdb_id_from_url(url):
    if not url:
        return ""

    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]

    for part in parts:
        if part.startswith("tt") and part[2:].isdigit():
            return part

    return ""


def enrich_movie_from_imdbapi(movie):
    imdb_id = imdb_id_from_url(movie.tmdb_url)

    if not imdb_id or movie.cast_names:
        return

    try:
        request = Request(
            f"https://api.imdbapi.dev/titles/{imdb_id}",
            headers={
                "accept": "application/json",
                "User-Agent": "CineVerseX/1.0 (+https://cineversex.onrender.com)",
            }
        )

        with urlopen(request, timeout=10) as response:
            details = json.loads(response.read().decode("utf-8"))
    except Exception as error:
        print("IMDbAPI detail enrich failed:", error)
        return

    runtime_seconds = details.get("runtimeSeconds") or 0
    primary_image = details.get("primaryImage") or {}

    movie.description = details.get("plot") or movie.description
    movie.runtime_minutes = movie.runtime_minutes or (int(runtime_seconds // 60) if runtime_seconds else None)
    movie.backdrop_url = movie.backdrop_url or primary_image.get("url") or movie.poster_url
    movie.cast_names = ", ".join(
        person.get("displayName", "")
        for person in details.get("stars", [])[:10]
        if person.get("displayName")
    )
    movie.director_names = ", ".join(
        person.get("displayName", "")
        for person in details.get("directors", [])[:4]
        if person.get("displayName")
    )
    movie.writer_names = ", ".join(
        person.get("displayName", "")
        for person in details.get("writers", [])[:4]
        if person.get("displayName")
    )

    db.session.commit()


def fetch_cached_imdb_images(tconsts):
    if not tconsts:
        return {}

    placeholders = ",".join("?" for _ in tconsts)

    try:
        with db.engine.connect() as connection:
            rows = connection.exec_driver_sql(
                f"""
                SELECT tconst, poster_url, backdrop_url
                FROM imdb_image_cache
                WHERE tconst IN ({placeholders})
                """,
                tuple(tconsts)
            ).fetchall()
    except Exception:
        return {}

    return {
        row[0]: {
            "poster_url": row[1] or "",
            "backdrop_url": row[2] or "",
        }
        for row in rows
    }


def cache_imdb_image(tconst, title, poster_url="", backdrop_url="", source="imdbapi"):
    with db.engine.begin() as connection:
        connection.exec_driver_sql(
            """
            INSERT INTO imdb_image_cache
                (tconst, title, poster_url, backdrop_url, source, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(tconst) DO UPDATE SET
                title = excluded.title,
                poster_url = excluded.poster_url,
                backdrop_url = excluded.backdrop_url,
                source = excluded.source,
                updated_at = excluded.updated_at
            """,
            (
                tconst,
                title or "",
                poster_url or "",
                backdrop_url or "",
                source,
                datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
        )


def fetch_imdbapi_image(tconst, title=""):
    try:
        api_request = Request(
            f"https://api.imdbapi.dev/titles/{tconst}",
            headers={
                "accept": "application/json",
                "User-Agent": "CineVerseX/1.0 (+https://cineversex.onrender.com)",
            }
        )

        with urlopen(api_request, timeout=8) as response:
            details = json.loads(response.read().decode("utf-8"))
    except Exception as error:
        print(f"IMDb image lookup failed for {tconst}:", error)
        return {}

    primary_image = details.get("primaryImage") or {}
    poster_url = primary_image.get("url") or ""

    if poster_url:
        cache_imdb_image(
            tconst,
            title or details.get("primaryTitle") or details.get("originalTitle") or "",
            poster_url,
            poster_url,
            "imdbapi"
        )

    return {
        "poster_url": poster_url,
        "backdrop_url": poster_url,
    }


def fetch_imdbapi_details(tconst):
    if not tconst:
        return {}

    try:
        api_request = Request(
            f"https://api.imdbapi.dev/titles/{tconst}",
            headers={
                "accept": "application/json",
                "User-Agent": "CineVerseX/1.0 (+https://cineversex.onrender.com)",
            }
        )

        with urlopen(api_request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as error:
        print(f"IMDb detail import failed for {tconst}:", error)
        return {}


def find_imdb_title(query):
    query = (query or "").strip()

    if not query or not imdb_db_available():
        return None

    conn = sqlite3.connect(f"file:{imdb_db_path()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if query.startswith("tt") and query[2:].isdigit():
        cur.execute(
            """
            SELECT
                t.tconst,
                t.primaryTitle,
                t.originalTitle,
                t.startYear,
                t.runtimeMinutes,
                t.genres,
                r.averageRating,
                r.numVotes
            FROM imdb_titles t
            LEFT JOIN imdb_ratings r ON t.tconst = r.tconst
            WHERE t.tconst = ?
            AND t.titleType = 'movie'
            AND t.isAdult = 0
            """,
            (query,)
        )
    else:
        cur.execute(
            """
            SELECT
                t.tconst,
                t.primaryTitle,
                t.originalTitle,
                t.startYear,
                t.runtimeMinutes,
                t.genres,
                r.averageRating,
                r.numVotes
            FROM imdb_titles t
            LEFT JOIN imdb_ratings r ON t.tconst = r.tconst
            WHERE t.titleType = 'movie'
            AND t.isAdult = 0
            AND (
                LOWER(t.primaryTitle) = LOWER(?)
                OR t.primaryTitle LIKE ?
                OR t.primaryTitle LIKE ?
            )
            ORDER BY
                CASE
                    WHEN LOWER(t.primaryTitle) = LOWER(?) THEN 0
                    WHEN t.primaryTitle LIKE ? THEN 1
                    ELSE 2
                END,
                COALESCE(r.numVotes, 0) DESC,
                COALESCE(r.averageRating, 0) DESC
            LIMIT 1
            """,
            (query, f"{query}%", f"%{query}%", query, f"{query}%")
        )

    row = cur.fetchone()
    conn.close()

    return dict(row) if row else None


def fetch_tmdb_movie_match(title, year=""):
    if not tmdb_is_configured() or not title:
        return {}

    params = {
        "query": title,
        "include_adult": "false",
        "language": "en-IN",
    }

    if str(year).isdigit():
        params["primary_release_year"] = str(year)

    try:
        data = fetch_tmdb_json("/search/movie", params)
    except Exception as error:
        print(f"TMDb import lookup failed for {title}:", error)
        return {}

    results = data.get("results") or []

    if not results and params.get("primary_release_year"):
        params.pop("primary_release_year", None)
        try:
            data = fetch_tmdb_json("/search/movie", params)
            results = data.get("results") or []
        except Exception:
            results = []

    best = next((item for item in results if item.get("poster_path")), results[0] if results else None)

    if not best:
        return {}

    return {
        "tmdb_id": best.get("id"),
        "title": best.get("title") or title,
        "description": best.get("overview") or "",
        "poster_url": f"{TMDB_IMAGE_BASE_URL}{best['poster_path']}" if best.get("poster_path") else "",
        "backdrop_url": f"{TMDB_IMAGE_BASE_URL}{best['backdrop_path']}" if best.get("backdrop_path") else "",
        "release_date": best.get("release_date") or "",
        "rating": round(float(best.get("vote_average") or 0), 1),
    }


def import_movie_from_external_sources(query):
    imdb_row = find_imdb_title(query)

    if not imdb_row:
        return None, "No matching movie found in the local IMDb database."

    title = imdb_row["primaryTitle"]
    existing_movie = Movie.query.filter(
        (Movie.title.ilike(title)) | (Movie.tmdb_url == f"https://www.imdb.com/title/{imdb_row['tconst']}/")
    ).first()

    imdb_details = fetch_imdbapi_details(imdb_row["tconst"])
    tmdb_match = fetch_tmdb_movie_match(title, imdb_row.get("startYear"))
    primary_image = imdb_details.get("primaryImage") or {}
    runtime_seconds = imdb_details.get("runtimeSeconds") or 0
    imdb_rating = imdb_details.get("rating") or {}
    poster_url = primary_image.get("url") or tmdb_match.get("poster_url") or ""
    backdrop_url = tmdb_match.get("backdrop_url") or primary_image.get("url") or poster_url
    description = (
        imdb_details.get("plot")
        or tmdb_match.get("description")
        or f"{title} imported from the local IMDb dataset."
    )
    languages = ", ".join(
        language.get("name", "")
        for language in imdb_details.get("spokenLanguages", [])
        if language.get("name")
    )
    cast_names = ", ".join(
        person.get("displayName", "")
        for person in imdb_details.get("stars", [])[:10]
        if person.get("displayName")
    )
    director_names = ", ".join(
        person.get("displayName", "")
        for person in imdb_details.get("directors", [])[:5]
        if person.get("displayName")
    )
    writer_names = ", ".join(
        person.get("displayName", "")
        for person in imdb_details.get("writers", [])[:5]
        if person.get("displayName")
    )

    if not existing_movie:
        existing_movie = Movie(title=title, description=description)
        db.session.add(existing_movie)

    existing_movie.title = title
    existing_movie.description = description
    existing_movie.poster_url = poster_url
    existing_movie.backdrop_url = backdrop_url
    existing_movie.language = languages or "Multiple Languages"
    existing_movie.genre = imdb_row.get("genres") or "Movie"
    existing_movie.release_date = (
        tmdb_match.get("release_date")
        or (str(int(imdb_row["startYear"])) if imdb_row.get("startYear") else "")
    )
    existing_movie.rating = round(float(
        imdb_rating.get("aggregateRating")
        or imdb_row.get("averageRating")
        or tmdb_match.get("rating")
        or 0
    ), 1)
    existing_movie.runtime_minutes = (
        int(runtime_seconds // 60)
        if runtime_seconds
        else (int(imdb_row["runtimeMinutes"]) if imdb_row.get("runtimeMinutes") else None)
    )
    existing_movie.certificate = existing_movie.certificate or "UA"
    existing_movie.cast_names = cast_names
    existing_movie.director_names = director_names
    existing_movie.writer_names = writer_names
    existing_movie.tmdb_id = tmdb_match.get("tmdb_id") or existing_movie.tmdb_id
    existing_movie.tmdb_url = f"https://www.imdb.com/title/{imdb_row['tconst']}/"
    existing_movie.justwatch_url = justwatch_search_url(title)
    existing_movie.bookmyshow_url = bookmyshow_search_url(title)
    existing_movie.bookmyshow_movie_url = existing_movie.bookmyshow_url
    existing_movie.bookmyshow_ticket_url = existing_movie.bookmyshow_url
    existing_movie.data_source = "imported"

    if poster_url:
        cache_imdb_image(imdb_row["tconst"], title, poster_url, backdrop_url, "import")

    db.session.commit()

    return existing_movie, ""


def fetch_imdb_movies(genre="", view="", sort="popular", page=1, limit=80):
    conn = sqlite3.connect(f"file:{imdb_db_path()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    page = max(page, 1)
    candidate_limit = limit * 3
    candidate_offset = max(page - 1, 0) * limit
    filters = [
        "t.titleType = 'movie'",
        "t.isAdult = 0",
    ]
    params = []

    if genre:
        filters.append("t.genres LIKE ?")
        params.append(f"%{genre}%")

    if view == "now-showing":
        filters.append("CAST(t.startYear AS INTEGER) = 2026")
    elif view == "upcoming":
        filters.append("CAST(t.startYear AS INTEGER) >= 2026")

    where_clause = " AND ".join(filters)

    if sort == "title":
        query = f"""
            SELECT
                t.tconst,
                t.primaryTitle,
                t.originalTitle,
                t.startYear,
                t.runtimeMinutes,
                t.genres,
                r.averageRating,
                r.numVotes
            FROM imdb_titles t
            LEFT JOIN imdb_ratings r ON t.tconst = r.tconst
            WHERE {where_clause}
            ORDER BY t.primaryTitle COLLATE NOCASE ASC
            LIMIT ?
            OFFSET ?
        """
    elif sort == "newest":
        query = f"""
            SELECT
                t.tconst,
                t.primaryTitle,
                t.originalTitle,
                t.startYear,
                t.runtimeMinutes,
                t.genres,
                r.averageRating,
                r.numVotes
            FROM imdb_titles t
            LEFT JOIN imdb_ratings r ON t.tconst = r.tconst
            WHERE {where_clause}
            ORDER BY CAST(t.startYear AS INTEGER) DESC, COALESCE(r.numVotes, 0) DESC
            LIMIT ?
            OFFSET ?
        """
    else:
        rating_order = "r.averageRating DESC, r.numVotes DESC" if sort == "rating" else "r.numVotes DESC, r.averageRating DESC"
        query = f"""
            SELECT
                t.tconst,
                t.primaryTitle,
                t.originalTitle,
                t.startYear,
                t.runtimeMinutes,
                t.genres,
                r.averageRating,
                r.numVotes
            FROM imdb_ratings r
            JOIN imdb_titles t ON t.tconst = r.tconst
            WHERE {where_clause}
            ORDER BY {rating_order}
            LIMIT ?
            OFFSET ?
        """

    cur.execute(query, params + [candidate_limit, candidate_offset])
    rows = cur.fetchall()
    conn.close()

    movies = []
    seen_titles = set()

    for row in rows:
        title_key = (
            (row["primaryTitle"] or "").strip().casefold(),
            int(row["startYear"] or 0)
        )

        if title_key in seen_titles:
            continue

        seen_titles.add(title_key)
        movies.append(dict(row))

        if len(movies) >= limit:
            break

    image_cache = fetch_cached_imdb_images([movie["tconst"] for movie in movies])

    for movie in movies:
        cached_image = image_cache.get(movie["tconst"], {})
        movie["poster_url"] = cached_image.get("poster_url", "")
        movie["backdrop_url"] = cached_image.get("backdrop_url", "")

    return movies


def count_imdb_movies(genre="", view=""):
    conn = sqlite3.connect(f"file:{imdb_db_path()}?mode=ro", uri=True)
    cur = conn.cursor()
    filters = [
        "titleType = 'movie'",
        "isAdult = 0",
    ]
    params = []

    if genre:
        filters.append("genres LIKE ?")
        params.append(f"%{genre}%")

    if view == "now-showing":
        filters.append("CAST(startYear AS INTEGER) = 2026")
    elif view == "upcoming":
        filters.append("CAST(startYear AS INTEGER) >= 2026")

    cur.execute(
        f"""
        SELECT COUNT(*)
        FROM imdb_titles
        WHERE {" AND ".join(filters)}
        """,
        params
    )
    total = cur.fetchone()[0]
    conn.close()

    return total


def fetch_imdb_movie(tconst):
    conn = sqlite3.connect(f"file:{imdb_db_path()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            t.tconst,
            t.primaryTitle,
            t.originalTitle,
            t.startYear,
            t.runtimeMinutes,
            t.genres,
            r.averageRating,
            r.numVotes
        FROM imdb_titles t
        LEFT JOIN imdb_ratings r ON t.tconst = r.tconst
        WHERE t.tconst = ?
        """,
        (tconst,)
    )
    movie = cur.fetchone()
    conn.close()

    return movie


def search_imdb_movies(query, limit=24, genre="", year="", min_rating=""):
    query = (query or "").strip()

    if not query or not imdb_db_available():
        return []

    conn = sqlite3.connect(f"file:{imdb_db_path()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    params = [f"{query}%"]
    filters = """
        SELECT
            t.tconst,
            t.primaryTitle,
            t.originalTitle,
            t.startYear,
            t.runtimeMinutes,
            t.genres,
            r.averageRating,
            r.numVotes
        FROM imdb_titles t
        LEFT JOIN imdb_ratings r ON t.tconst = r.tconst
        WHERE t.titleType = 'movie'
        AND t.isAdult = 0
        AND t.primaryTitle LIKE ?
    """

    if genre:
        filters += " AND t.genres LIKE ?"
        params.append(f"%{genre}%")

    if year:
        filters += " AND t.startYear = ?"
        params.append(year)

    if min_rating:
        filters += " AND COALESCE(r.averageRating, 0) >= ?"
        params.append(float(min_rating))

    filters += """
        ORDER BY
            CASE
                WHEN LOWER(t.primaryTitle) = LOWER(?) THEN 0
                WHEN t.primaryTitle LIKE ? THEN 1
                ELSE 2
            END,
            COALESCE(r.numVotes, 0) DESC,
            COALESCE(r.averageRating, 0) DESC
        LIMIT ?
        """
    params.extend([query, f"{query}%", limit])
    cur.execute(filters, params)
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()

    image_cache = fetch_cached_imdb_images([movie["tconst"] for movie in rows])

    for movie in rows:
        cached_image = image_cache.get(movie["tconst"], {})
        movie["poster_url"] = cached_image.get("poster_url", "")
        movie["backdrop_url"] = cached_image.get("backdrop_url", "")

    return rows


@movie_bp.route("/imdb/poster/<tconst>")
def imdb_poster(tconst):
    title = request.args.get("title", "")
    cached = fetch_cached_imdb_images([tconst]).get(tconst, {})
    poster_url = cached.get("poster_url")

    if poster_url:
        return redirect(poster_url)

    fetched = fetch_imdbapi_image(tconst, title)

    if fetched.get("poster_url"):
        return redirect(fetched["poster_url"])

    safe_title = escape(title or "IMDb Movie")
    initial = escape((title or "M")[:1].upper())
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="640" height="960" viewBox="0 0 640 960">
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#171321"/>
    <stop offset="1" stop-color="#050505"/>
  </linearGradient>
</defs>
<rect width="640" height="960" fill="url(#bg)"/>
<circle cx="320" cy="270" r="118" fill="#f84464" opacity=".88"/>
<text x="320" y="312" text-anchor="middle" font-family="Arial, sans-serif" font-size="128" font-weight="900" fill="#fff">{initial}</text>
<text x="64" y="690" font-family="Arial, sans-serif" font-size="52" font-weight="900" fill="#fff">{safe_title}</text>
<text x="64" y="752" font-family="Arial, sans-serif" font-size="28" font-weight="700" fill="#f8c8d2">IMDb dataset title</text>
<text x="64" y="820" font-family="Arial, sans-serif" font-size="22" font-weight="700" fill="#f4e6df">Poster will cache when a public image is available</text>
</svg>"""
    return Response(svg, mimetype="image/svg+xml")


@movie_bp.route("/movies")
def movies():
    selected_genre = request.args.get("genre", "")
    selected_view = request.args.get("view", "upcoming")
    selected_sort = request.args.get("sort", "popular")
    is_admin = current_user.is_authenticated and getattr(current_user, "role", "") == "admin"
    selected_source = request.args.get("source") or ("imdb" if is_admin and imdb_db_available() else "local")
    if selected_source == "imdb" and not is_admin:
        selected_source = "local"
    selected_page = max(request.args.get("page", 1, type=int), 1)
    per_page = 36
    today_key = datetime.utcnow().strftime("%Y-%m-%d")

    if selected_source == "imdb":
        if imdb_db_available():
            total_movies = count_imdb_movies(selected_genre, selected_view)
            total_pages = max((total_movies + per_page - 1) // per_page, 1)
            selected_page = min(selected_page, total_pages)
            imdb_movies = fetch_imdb_movies(
                selected_genre,
                selected_view,
                selected_sort,
                page=selected_page,
                limit=per_page
            )
            return render_template(
                "movies.html",
                movies=imdb_movies,
                genres=GENRES,
                selected_genre=selected_genre,
                selected_view=selected_view,
                selected_sort=selected_sort,
                selected_source=selected_source,
                selected_page=selected_page,
                movie_source="imdb",
                is_admin=is_admin,
                imdb_database_label=imdb_database_label(),
                bookmyshow_search_url=bookmyshow_search_url,
                total_pages=total_pages,
                pagination_pages=pagination_window(selected_page, total_pages)
            )

        return render_template(
            "movies.html",
            movies=[],
            genres=GENRES,
            selected_genre=selected_genre,
            selected_view=selected_view,
            selected_sort=selected_sort,
            selected_source=selected_source,
            selected_page=selected_page,
            movie_source="imdb",
            is_admin=is_admin,
            bookmyshow_search_url=bookmyshow_search_url,
            total_pages=1,
            pagination_pages=[],
            imdb_status_message=(
                "IMDb database is not connected locally. "
                f"Expected database path: {imdb_db_path()}"
            )
        )

    local_query = Movie.query.filter(Movie.data_source.in_(("tmdb", "imdbapi", "curated")))

    if local_query.count() > 0:
        if selected_genre:
            local_query = local_query.filter(Movie.genre.ilike(f"%{selected_genre}%"))

        if selected_view == "now-showing":
            local_query = local_query.filter(Movie.release_date <= today_key)
        elif selected_view == "upcoming":
            local_query = local_query.filter(Movie.release_date >= today_key)

        poster_query = local_query.filter(Movie.poster_url.isnot(None), Movie.poster_url != "")

        if poster_query.count() >= 24:
            local_query = poster_query

        poster_first = Movie.poster_url.isnot(None).desc(), (Movie.poster_url != "").desc()

        if selected_sort == "rating":
            local_query = local_query.order_by(*poster_first, Movie.rating.desc(), Movie.title.asc())
        elif selected_sort == "newest":
            local_query = local_query.order_by(*poster_first, Movie.release_date.desc(), Movie.rating.desc())
        elif selected_sort == "title":
            local_query = local_query.order_by(*poster_first, Movie.title.asc())
        else:
            local_query = local_query.order_by(*poster_first, Movie.release_date.asc(), Movie.rating.desc())

        total_movies = local_query.count()
        total_pages = max((total_movies + per_page - 1) // per_page, 1)
        selected_page = min(selected_page, total_pages)

        return render_template(
            "movies.html",
            movies=local_query.offset((selected_page - 1) * per_page).limit(per_page).all(),
            genres=GENRES,
            selected_genre=selected_genre,
            selected_view=selected_view,
            selected_sort=selected_sort,
            selected_source=selected_source,
            selected_page=selected_page,
            movie_source="local",
            is_admin=is_admin,
            total_pages=total_pages,
            pagination_pages=pagination_window(selected_page, total_pages)
        )

    if is_admin and imdb_db_available():
        total_movies = count_imdb_movies(selected_genre, selected_view)
        total_pages = max((total_movies + per_page - 1) // per_page, 1)
        selected_page = min(selected_page, total_pages)
        imdb_movies = fetch_imdb_movies(selected_genre, selected_view, selected_sort, page=selected_page, limit=per_page)
        return render_template(
            "movies.html",
            movies=imdb_movies,
            genres=GENRES,
            selected_genre=selected_genre,
            selected_view=selected_view,
            selected_sort=selected_sort,
            selected_source="imdb",
            selected_page=selected_page,
            movie_source="imdb",
            is_admin=is_admin,
            imdb_database_label=imdb_database_label(),
            bookmyshow_search_url=bookmyshow_search_url,
            total_pages=total_pages,
            pagination_pages=pagination_window(selected_page, total_pages)
        )

    return render_template(
        "movies.html",
        movies=[],
        genres=GENRES,
        selected_genre=selected_genre,
        selected_view=selected_view,
        selected_sort=selected_sort,
        selected_source="local",
        selected_page=selected_page,
        movie_source="local",
        is_admin=is_admin,
        bookmyshow_search_url=bookmyshow_search_url,
        total_pages=1,
        pagination_pages=[],
        imdb_status_message=(
            "IMDb database is not connected. "
            f"Expected database path: {imdb_db_path()}"
        )
    )


@movie_bp.route("/imdb/movie/<tconst>")
@admin_required
def imdb_movie_details(tconst):
    if not imdb_db_available():
        return "IMDb database not found", 404

    movie = fetch_imdb_movie(tconst)

    if not movie:
        return "IMDb movie not found", 404

    return render_template(
        "imdb_movie_details.html",
        movie=movie,
        bookmyshow_url=bookmyshow_search_url(movie["primaryTitle"]),
        justwatch_url=justwatch_search_url(movie["primaryTitle"])
    )


def normalize_youtube_embed_url(url):
    url = (url or "").strip()

    if not url:
        return ""

    parsed = urlparse(url)
    host = parsed.netloc.lower().replace("www.", "")
    video_id = ""

    if host in {"youtube.com", "m.youtube.com"}:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        elif parsed.path.startswith("/embed/"):
            video_id = parsed.path.split("/embed/", 1)[1].split("/", 1)[0]
        elif parsed.path.startswith("/shorts/"):
            video_id = parsed.path.split("/shorts/", 1)[1].split("/", 1)[0]
    elif host == "youtu.be":
        video_id = parsed.path.strip("/").split("/", 1)[0]

    if video_id:
        return f"https://www.youtube.com/embed/{video_id}"

    return url


def youtube_watch_url(embed_url):
    embed_url = (embed_url or "").strip()

    if "/embed/" not in embed_url:
        return embed_url

    video_id = embed_url.split("/embed/", 1)[1].split("?", 1)[0].split("/", 1)[0]
    return f"https://www.youtube.com/watch?v={video_id}"


@movie_bp.route("/add-movie", methods=["GET", "POST"])
@admin_required
def add_movie():

    if request.method == "POST":
        import_query = (request.form.get("import_query") or "").strip()

        if import_query:
            imported_movie, error = import_movie_from_external_sources(import_query)

            if error:
                flash(error, "danger")
                return redirect(url_for("movie_bp.add_movie"))

            flash(f"{imported_movie.title} imported successfully.", "success")
            log_activity("Movie Added", f"Imported movie: {imported_movie.title}", notify=True)
            return redirect(url_for("movie_bp.movie_details", movie_id=imported_movie.id))

        title = request.form["title"].strip()
        description = request.form["description"].strip()
        language = request.form["language"].strip()
        genre = request.form.get("genre", "").strip()
        release_date = request.form["release_date"].strip()
        rating = float(request.form["rating"] or 0)
        trailer_url = normalize_youtube_embed_url(request.form.get("trailer_url"))
        justwatch_url = (request.form.get("justwatch_url") or "").strip()
        bookmyshow_url = (request.form.get("bookmyshow_url") or "").strip()

        existing_movie = Movie.query.filter_by(title=title).first()

        if existing_movie:
            return "Movie already exists"

        poster_file = request.files.get("poster")
        poster_url = ""

        if poster_file and poster_file.filename:
            if not allowed_file(poster_file.filename):
                return "Only PNG, JPG, JPEG, and WEBP images are allowed"

            original_filename = secure_filename(poster_file.filename)
            extension = original_filename.rsplit(".", 1)[1].lower()
            unique_filename = f"{uuid4().hex}.{extension}"

            poster_folder = os.path.join(
                current_app.root_path,
                "static",
                "posters"
            )

            if not os.path.isdir(poster_folder):
                os.makedirs(poster_folder)

            poster_path = os.path.join(
                poster_folder,
                unique_filename
            )

            poster_file.save(poster_path)

            poster_url = f"posters/{unique_filename}"

        movie = Movie(
            title=title,
            description=description,
            poster_url=poster_url,
            language=language,
            genre=genre,
            release_date=release_date,
            rating=rating,
            trailer_url=trailer_url,
            justwatch_url=justwatch_url,
            bookmyshow_url=bookmyshow_url
        )

        if not movie.poster_url:
            return "Please upload a poster image"

        db.session.add(movie)
        db.session.commit()
        log_activity("Movie Added", f"Added movie: {movie.title}", notify=True)

        return redirect(url_for("movie_bp.movies"))

    return render_template("add_movie.html")


@movie_bp.route("/movie/<int:movie_id>")
def movie_details(movie_id):

    movie = Movie.query.get_or_404(movie_id)
    enrich_movie_from_imdbapi(movie)
    reviews = Review.query.filter_by(movie_id=movie_id)\
        .order_by(Review.created_at.desc())\
        .all()
    avg_rating = db.session.query(
        func.avg(Review.rating)
    ).filter_by(movie_id=movie_id).scalar()

    shows = Show.query.filter_by(
        movie_id=movie.id
    ).all()

    similar_movies = Movie.query.filter(
        Movie.id != movie.id,
        Movie.genre.ilike(f"%{(movie.genre or '').split(',')[0].strip()}%")
    ).order_by(Movie.rating.desc()).limit(4).all() if movie.genre else []

    theaters = {}

    for show in shows:
        theater = Theater.query.get(show.theater_id)

        if theater:
            if theater.id not in theaters:
                theaters[theater.id] = {
                    "theater": theater,
                    "shows": []
                }

            theaters[theater.id]["shows"].append(show)

    return render_template(
        "movie_details.html",
        movie=movie,
        theaters=theaters,
        reviews=reviews,
        avg_rating=round(avg_rating, 1) if avg_rating else 0,
        trailer_watch_url=youtube_watch_url(movie.trailer_url),
        similar_movies=similar_movies,
        justwatch_url=movie.justwatch_url or justwatch_search_url(movie.title)
    )


@movie_bp.route("/movie/<int:movie_id>/review", methods=["POST"])
@login_required
def add_review(movie_id):
    Movie.query.get_or_404(movie_id)

    try:
        rating = int(request.form.get("rating", 0))
    except ValueError:
        rating = 0

    comment = (request.form.get("comment") or "").strip()

    if rating < 1 or rating > 5:
        flash("Rating must be between 1 and 5.", "danger")
        return redirect(url_for("movie_bp.movie_details", movie_id=movie_id))

    existing_review = Review.query.filter_by(
        user_id=current_user.id,
        movie_id=movie_id
    ).first()

    if existing_review:
        existing_review.rating = rating
        existing_review.comment = comment
    else:
        review = Review(
            user_id=current_user.id,
            movie_id=movie_id,
            rating=rating,
            comment=comment
        )
        db.session.add(review)

    db.session.commit()
    flash("Review submitted successfully.", "success")
    return redirect(url_for("movie_bp.movie_details", movie_id=movie_id))


@movie_bp.route("/search")
def search_movies():

    query = request.args.get("q", "").strip()
    selected_genre = request.args.get("genre", "").strip()
    selected_year = request.args.get("year", "").strip()
    selected_rating = request.args.get("rating", "").strip()

    movies_query = Movie.query

    if query:
        search_tokens = [
            token
            for token in query.replace("-", " ").replace(":", " ").split()
            if token.strip()
        ]

        token_filters = []

        for token in search_tokens:
            like_query = f"%{token}%"
            token_filters.append(or_(
                Movie.title.ilike(like_query),
                Movie.genre.ilike(like_query),
                Movie.language.ilike(like_query),
                Movie.description.ilike(like_query),
            ))

        if token_filters:
            movies_query = movies_query.filter(or_(*token_filters))

    if selected_genre:
        movies_query = movies_query.filter(Movie.genre.ilike(f"%{selected_genre}%"))

    if selected_year:
        movies_query = movies_query.filter(Movie.release_date.ilike(f"{selected_year}%"))

    if selected_rating:
        movies_query = movies_query.filter(Movie.rating >= float(selected_rating))

    movies = movies_query.order_by(Movie.release_date.desc(), Movie.rating.desc()).limit(36).all()
    is_admin = current_user.is_authenticated and getattr(current_user, "role", "") == "admin"
    imdb_movies = []

    if is_admin:
        imdb_movies = search_imdb_movies(
            query,
            limit=12,
            genre=selected_genre,
            year=selected_year,
            min_rating=selected_rating
        )

    return render_template(
        "search_results.html",
        movies=movies,
        imdb_movies=imdb_movies,
        query=query,
        genres=GENRES,
        selected_genre=selected_genre,
        selected_year=selected_year,
        selected_rating=selected_rating,
        is_admin=is_admin
    )
@movie_bp.route("/edit-movie/<int:movie_id>", methods=["GET", "POST"])
@admin_required
def edit_movie(movie_id):

    movie = Movie.query.get_or_404(movie_id)

    if request.method == "POST":

        movie.title = request.form["title"]
        movie.description = request.form["description"]
        movie.language = request.form["language"]
        movie.genre = request.form.get("genre", "").strip()
        movie.release_date = request.form["release_date"]
        movie.rating = float(request.form["rating"])
        movie.trailer_url = normalize_youtube_embed_url(request.form.get("trailer_url"))
        movie.justwatch_url = (request.form.get("justwatch_url") or "").strip()
        movie.bookmyshow_url = (request.form.get("bookmyshow_url") or "").strip()

        db.session.commit()
        log_activity("Movie Edited", f"Edited movie: {movie.title}", notify=True)

        return redirect(url_for("movie_bp.movie_details", movie_id=movie.id))

    return render_template(
        "edit_movie.html",
        movie=movie,
        genres=GENRES,
        trailer_watch_url=youtube_watch_url(movie.trailer_url)
    )
@movie_bp.route("/delete-movie/<int:movie_id>")
@admin_required
def delete_movie(movie_id):

    movie = Movie.query.get_or_404(movie_id)
    title = movie.title

    db.session.delete(movie)
    db.session.commit()
    log_activity("Movie Deleted", f"Deleted movie: {title}", notify=True)

    return redirect(url_for("movie_bp.movies"))
