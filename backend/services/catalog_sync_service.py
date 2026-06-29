import json
import os
import sqlite3
from datetime import datetime, timedelta
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen

from flask import current_app

from extensions import db
from models.movie import Movie
from models.setting import SystemSetting
from models.show import Show
from models.theater import Screen, Theater
from services.catalog_data import (
    BOOKMYSHOW_HOME_URL,
    CURATED_UPCOMING_RELEASES,
    FEATURED_MOVIE_DETAILS,
    IMDBAPI_BASE_URL,
    KNOWN_BOOKMYSHOW_LINKS,
    THEATER_NETWORK,
    THEATER_RENAMES,
    TMDB_BASE_URL,
    TMDB_IMAGE_BASE_URL,
)

def booking_catalog_imdb_path():
    configured_path = current_app.config.get("IMDB_DB_PATH", "").strip()

    if configured_path:
        return os.path.abspath(configured_path)

    deploy_disk_path = os.path.abspath("/var/data/cineversex.db")

    if os.path.isfile(deploy_disk_path):
        return deploy_disk_path

    return os.path.abspath(os.path.join(current_app.root_path, "..", "cineversex.db"))


def normalize_title_key(title):
    return " ".join((title or "").strip().lower().split())


def bookmyshow_search_url(title):
    title = (title or "").strip()

    if not title:
        return BOOKMYSHOW_HOME_URL

    return KNOWN_BOOKMYSHOW_LINKS.get(
        normalize_title_key(title),
        f"https://in.bookmyshow.com/search?q={quote_plus(title)}"
    )


def normalize_bookmyshow_movie_url(url):
    cleaned_url = (url or "").strip()
    return cleaned_url or BOOKMYSHOW_HOME_URL


def bookmyshow_links_for_title(title):
    direct_url = bookmyshow_search_url(title)
    return {
        "movie": direct_url,
        "ticket": direct_url if direct_url != BOOKMYSHOW_HOME_URL else "",
        "primary": direct_url,
    }


def tmdb_headers():
    bearer_token = os.environ.get("TMDB_BEARER_TOKEN", "").strip()

    if bearer_token:
        return {"Authorization": f"Bearer {bearer_token}"}

    return {}


def tmdb_url(path, params=None):
    params = params or {}
    api_key = os.environ.get("TMDB_API_KEY", "").strip()

    if api_key and not os.environ.get("TMDB_BEARER_TOKEN", "").strip():
        params["api_key"] = api_key

    return f"{TMDB_BASE_URL}{path}?{urlencode(params)}"


def tmdb_is_configured():
    return bool(
        os.environ.get("TMDB_BEARER_TOKEN", "").strip()
        or os.environ.get("TMDB_API_KEY", "").strip()
    )


def fetch_tmdb_json(path, params=None):
    request = Request(
        tmdb_url(path, params),
        headers=tmdb_headers()
    )

    with urlopen(request, timeout=8) as response:
        return json.loads(response.read().decode("utf-8"))


def imdbapi_url(path, params=None):
    query = f"?{urlencode(params or {}, doseq=True)}" if params else ""
    return f"{IMDBAPI_BASE_URL}{path}{query}"


def fetch_imdbapi_json(path, params=None, timeout=12):
    request = Request(
        imdbapi_url(path, params),
        headers={
            "accept": "application/json",
            "User-Agent": "CineVerseX/1.0 (+https://cineversex.onrender.com)",
        }
    )

    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def precision_date_to_iso(value):
    if not value:
        return ""

    year = value.get("year")
    month = value.get("month")
    day = value.get("day")

    if year and month and day:
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"

    if year and month:
        return f"{int(year):04d}-{int(month):02d}-01"

    if year:
        return f"{int(year):04d}-12-31"

    return ""


def fetch_imdbapi_release_date(title_id):
    if not title_id:
        return ""

    try:
        response = fetch_imdbapi_json(f"/titles/{title_id}/releaseDates", timeout=8)
    except Exception:
        return ""

    release_dates = response.get("releaseDates", [])

    for preferred_code in ("IN", "US", "GB"):
        for item in release_dates:
            country = item.get("country") or {}

            if country.get("code") == preferred_code:
                return precision_date_to_iso(item.get("releaseDate"))

    for item in release_dates:
        release_date = precision_date_to_iso(item.get("releaseDate"))

        if release_date:
            return release_date

    return ""


def normalize_imdbapi_title(item, fetch_release_date=False):
    title = item.get("primaryTitle") or item.get("originalTitle")

    if not title:
        return None

    title_id = item.get("id") or ""
    genres = ", ".join(item.get("genres") or [])
    languages = ", ".join(
        language.get("name", "")
        for language in item.get("spokenLanguages", [])
        if language.get("name")
    )
    rating = item.get("rating") or {}
    poster = item.get("primaryImage") or {}
    year = item.get("startYear")
    runtime_seconds = item.get("runtimeSeconds") or 0
    cast_names = ", ".join(
        person.get("displayName", "")
        for person in item.get("stars", [])[:8]
        if person.get("displayName")
    )
    director_names = ", ".join(
        person.get("displayName", "")
        for person in item.get("directors", [])[:4]
        if person.get("displayName")
    )
    writer_names = ", ".join(
        person.get("displayName", "")
        for person in item.get("writers", [])[:4]
        if person.get("displayName")
    )
    release_date = (fetch_imdbapi_release_date(title_id) if fetch_release_date else "") or (
        f"{int(year):04d}-12-31" if year else ""
    )

    return {
        "imdb_id": title_id,
        "title": title,
        "description": item.get("plot") or "IMDbAPI synced release details will update as official metadata becomes available.",
        "poster_url": poster.get("url") or "",
        "language": languages or "English, Hindi, Tamil, Telugu",
        "genre": genres or "Drama",
        "release_date": release_date,
        "rating": round(float(rating.get("aggregateRating") or 0), 1),
        "runtime_minutes": int(runtime_seconds // 60) if runtime_seconds else None,
        "certificate": "UA",
        "cast_names": cast_names,
        "director_names": director_names,
        "writer_names": writer_names,
        "backdrop_url": poster.get("url") or "",
    }


def fetch_booking_catalog_from_imdbapi(limit=120, max_pages=4):
    current_year = datetime.utcnow().year

    movies = []
    seen_titles = set()
    page_token = ""

    for _ in range(max_pages):
        params = {
            "types": ["MOVIE"],
            "startYear": current_year,
            "endYear": current_year + 2,
            "sortBy": "SORT_BY_RELEASE_DATE",
            "sortOrder": "ASC",
            "minVoteCount": 0,
        }

        if page_token:
            params["pageToken"] = page_token

        try:
            response = fetch_imdbapi_json("/titles", params)
        except Exception as error:
            print("IMDbAPI sync failed:", error)
            break

        for item in response.get("titles", []):
            normalized = normalize_imdbapi_title(item)

            if not normalized or not normalized["poster_url"]:
                continue

            title_key = (
                normalized["title"].strip().casefold(),
                normalized["release_date"][:4],
            )

            if title_key in seen_titles:
                continue

            seen_titles.add(title_key)
            movies.append(normalized)

            if len(movies) >= limit:
                return movies

        page_token = response.get("nextPageToken") or ""

        if not page_token:
            break

    return movies


def fetch_booking_catalog_from_tmdb(region="IN", pages=2):
    if not tmdb_is_configured():
        return []

    genre_response = fetch_tmdb_json(
        "/genre/movie/list",
        {"language": "en-US"}
    )
    genre_map = {
        genre["id"]: genre["name"]
        for genre in genre_response.get("genres", [])
    }

    movies = []
    seen_tmdb_ids = set()

    for endpoint in ("/movie/now_playing", "/movie/upcoming"):
        for page in range(1, pages + 1):
            response = fetch_tmdb_json(
                endpoint,
                {
                    "language": "en-US",
                    "region": region,
                    "page": page,
                }
            )

            for item in response.get("results", []):
                tmdb_id = item.get("id")

                if not tmdb_id or tmdb_id in seen_tmdb_ids:
                    continue

                seen_tmdb_ids.add(tmdb_id)
                title = item.get("title") or item.get("name")

                if not title:
                    continue

                genres = ", ".join(
                    genre_map.get(genre_id, "")
                    for genre_id in item.get("genre_ids", [])
                    if genre_map.get(genre_id)
                )

                poster_path = item.get("poster_path")
                movies.append({
                    "tmdb_id": tmdb_id,
                    "title": title,
                    "description": item.get("overview") or "No synopsis available yet.",
                    "poster_url": f"{TMDB_IMAGE_BASE_URL}{poster_path}" if poster_path else "",
                    "backdrop_url": f"{TMDB_IMAGE_BASE_URL}{item.get('backdrop_path')}" if item.get("backdrop_path") else "",
                    "language": (item.get("original_language") or "en").upper(),
                    "genre": genres or "Drama",
                    "release_date": item.get("release_date") or "",
                    "rating": round(float(item.get("vote_average") or 0), 1),
                })

    return movies


def fetch_booking_catalog_from_imdb(limit=10):
    imdb_path = booking_catalog_imdb_path()

    if not os.path.isfile(imdb_path):
        return []

    conn = sqlite3.connect(f"file:{imdb_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT
            t.primaryTitle,
            t.startYear,
            t.genres,
            r.averageRating,
            r.numVotes
        FROM imdb_titles t
        LEFT JOIN imdb_ratings r ON t.tconst = r.tconst
        WHERE t.titleType = 'movie'
        AND t.isAdult = 0
        AND t.startYear >= 2026
        GROUP BY t.primaryTitle, t.startYear
        ORDER BY
            COALESCE(r.numVotes, 0) DESC,
            COALESCE(r.averageRating, 0) DESC
        LIMIT ?
        """,
        (limit,)
    ).fetchall()
    conn.close()

    return rows


def ensure_screen(theater, screen_name, total_seats):
    screen = Screen.query.filter_by(
        theater_id=theater.id,
        screen_name=screen_name
    ).first()

    if not screen:
        screen = Screen(
            theater_id=theater.id,
            screen_name=screen_name,
            total_seats=total_seats
        )
        db.session.add(screen)
    else:
        screen.total_seats = total_seats

    return screen


def fetch_tmdb_image_match(title, release_date=""):
    if not tmdb_is_configured() or not title:
        return None

    year = (release_date or "")[:4]
    params = {
        "query": title,
        "include_adult": "false",
        "language": "en-IN",
    }

    if year.isdigit():
        params["primary_release_year"] = year

    response = fetch_tmdb_json("/search/movie", params)
    results = response.get("results", [])

    if not results and year.isdigit():
        params.pop("primary_release_year", None)
        response = fetch_tmdb_json("/search/movie", params)
        results = response.get("results", [])

    best = next((item for item in results if item.get("poster_path")), None)

    if not best:
        return None

    return {
        "tmdb_id": best.get("id"),
        "poster_url": f"{TMDB_IMAGE_BASE_URL}{best['poster_path']}",
        "backdrop_url": (
            f"{TMDB_IMAGE_BASE_URL}{best['backdrop_path']}"
            if best.get("backdrop_path")
            else ""
        ),
    }


def backfill_missing_movie_posters(limit=80):
    if not tmdb_is_configured():
        return False

    movies = (
        Movie.query
        .filter(Movie.data_source.in_(("curated", "manual")))
        .filter((Movie.poster_url.is_(None)) | (Movie.poster_url == ""))
        .order_by(Movie.release_date.asc(), Movie.title.asc())
        .limit(limit)
        .all()
    )

    updated = 0

    for movie in movies:
        try:
            match = fetch_tmdb_image_match(movie.title, movie.release_date)
        except Exception as error:
            print(f"TMDb poster lookup failed for {movie.title}:", error)
            continue

        if not match:
            continue

        movie.poster_url = match["poster_url"]
        movie.backdrop_url = match["backdrop_url"] or match["poster_url"]

        if match.get("tmdb_id") and not movie.tmdb_id:
            movie.tmdb_id = match["tmdb_id"]
            movie.tmdb_url = f"https://www.themoviedb.org/movie/{match['tmdb_id']}"

        db.session.commit()
        updated += 1

    return bool(updated)


def sync_theater_network():
    for old_name, (new_name, new_city, new_address) in THEATER_RENAMES.items():
        old_theater = Theater.query.filter_by(name=old_name).first()

        if not old_theater:
            continue

        duplicate = Theater.query.filter_by(name=new_name, city=new_city).first()

        if duplicate and duplicate.id != old_theater.id:
            for screen in old_theater.screens:
                screen.theater_id = duplicate.id

            for show in old_theater.shows:
                show.theater_id = duplicate.id

            db.session.delete(old_theater)
        else:
            old_theater.name = new_name
            old_theater.city = new_city
            old_theater.address = new_address

    db.session.flush()

    for name, city, address, total_screens, base_seats in THEATER_NETWORK:
        theater = Theater.query.filter_by(name=name, city=city).first()

        if not theater:
            theater = Theater(
                name=name,
                city=city,
                address=address,
                total_screens=total_screens
            )
            db.session.add(theater)
            db.session.flush()
        else:
            theater.address = address
            theater.total_screens = total_screens

        for index in range(1, total_screens + 1):
            screen_label = (
                f"IMAX Screen {index}"
                if index == 1 and total_screens >= 5
                else f"Screen {index}"
            )
            ensure_screen(theater, screen_label, base_seats + (index * 12))

    db.session.commit()


def sync_booking_catalog_from_imdb():
    imdb_rows = fetch_booking_catalog_from_imdb()

    if not imdb_rows:
        return

    theater_seed = THEATER_NETWORK[:8]

    theaters = []

    for name, city, address, total_screens, *_ in theater_seed:
        theater = Theater.query.filter_by(name=name, city=city).first()

        if not theater:
            theater = Theater(
                name=name,
                city=city,
                address=address,
                total_screens=total_screens
            )
            db.session.add(theater)
            db.session.flush()
        else:
            theater.address = address
            theater.total_screens = total_screens

        for index in range(1, total_screens + 1):
            ensure_screen(theater, f"Screen {index}", 96 + (index * 18))

        theaters.append(theater)

    db.session.flush()

    movies = []

    for row in imdb_rows:
        title = row["primaryTitle"]
        year = str(int(row["startYear"])) if row["startYear"] else "2026"
        genres = row["genres"] or "Drama"
        rating = float(row["averageRating"] or 0)

        movie = Movie.query.filter_by(title=title).first()

        if not movie:
            movie = Movie(
                title=title,
                description="Freshly synced from the IMDb dataset for CineVerse booking availability.",
                language="English",
                genre=genres,
                release_date=year,
                rating=rating,
                poster_url=""
            )
            db.session.add(movie)
        else:
            movie.genre = genres
            movie.release_date = year
            movie.rating = rating

        encoded_title = quote_plus(title)
        bookmyshow_links = bookmyshow_links_for_title(title)
        movie.bookmyshow_movie_url = bookmyshow_links["movie"]
        movie.bookmyshow_ticket_url = bookmyshow_links["ticket"]
        movie.bookmyshow_url = bookmyshow_links["primary"]
        movie.justwatch_url = f"https://www.justwatch.com/in/search?q={encoded_title}"
        movies.append(movie)

    db.session.flush()

    base_day = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    show_times = ("10:30", "13:45", "17:15", "20:45")
    prices = (180, 220, 260, 320)

    for movie_index, movie in enumerate(movies):
        for slot_index in range(2):
            theater = theaters[(movie_index + slot_index) % len(theaters)]
            screens = Screen.query.filter_by(theater_id=theater.id).order_by(Screen.id.asc()).all()
            screen = screens[slot_index % len(screens)]
            day = base_day + timedelta(days=movie_index % 5)
            show_time = f"{day.date()} {show_times[(movie_index + slot_index) % len(show_times)]}"

            existing_show = Show.query.filter_by(
                movie_id=movie.id,
                theater_id=theater.id,
                screen_id=screen.id,
                show_time=show_time
            ).first()

            if existing_show:
                existing_show.price = prices[(movie_index + slot_index) % len(prices)]
                continue

            db.session.add(
                Show(
                    movie_id=movie.id,
                    theater_id=theater.id,
                    screen_id=screen.id,
                    show_time=show_time,
                    price=prices[(movie_index + slot_index) % len(prices)]
                )
            )

    db.session.commit()


def sync_curated_upcoming_catalog():
    theater = Theater.query.filter_by(name="BookMyShow", city="Bengaluru").first()

    if not theater:
        theater = Theater(
            name="BookMyShow",
            city="Bengaluru",
            address="External booking partner",
            total_screens=1
        )
        db.session.add(theater)
        db.session.flush()

    screen = ensure_screen(theater, "External Booking", 0)
    db.session.flush()

    show_time = "10:00"

    for item in CURATED_UPCOMING_RELEASES:
        movie = Movie.query.filter_by(title=item["title"]).first()

        if not movie:
            movie = Movie(
                title=item["title"],
                description=item["description"]
            )
            db.session.add(movie)

        movie.description = item["description"]
        movie.poster_url = ""
        movie.backdrop_url = movie.backdrop_url or ""
        movie.language = item["language"]
        movie.genre = item["genre"]
        movie.release_date = item["release_date"]
        movie.rating = item["rating"]
        movie.certificate = movie.certificate or "UA"
        movie.data_source = "curated"

        bookmyshow_links = bookmyshow_links_for_title(item["title"])
        movie.bookmyshow_movie_url = bookmyshow_links["movie"]
        movie.bookmyshow_ticket_url = bookmyshow_links["ticket"]
        movie.bookmyshow_url = bookmyshow_links["primary"]
        movie.justwatch_url = f"https://www.justwatch.com/in/search?q={quote_plus(item['title'])}"

        db.session.flush()

        existing_show = Show.query.filter_by(
            movie_id=movie.id,
            theater_id=theater.id,
            screen_id=screen.id
        ).first()

        if existing_show:
            existing_show.show_time = f"{item['release_date']} {show_time}"
            existing_show.price = 0
            continue

        db.session.add(
            Show(
                movie_id=movie.id,
                theater_id=theater.id,
                screen_id=screen.id,
                show_time=f"{item['release_date']} {show_time}",
                price=0
            )
        )

    db.session.commit()


def sync_booking_catalog_from_imdbapi():
    imdbapi_movies = fetch_booking_catalog_from_imdbapi()

    if not imdbapi_movies:
        return False

    theater = Theater.query.filter_by(name="BookMyShow", city="Bengaluru").first()

    if not theater:
        theater = Theater(
            name="BookMyShow",
            city="Bengaluru",
            address="External booking partner",
            total_screens=1
        )
        db.session.add(theater)
        db.session.flush()

    screen = ensure_screen(theater, "External Booking", 0)
    db.session.flush()

    for item in imdbapi_movies:
        movie = Movie.query.filter_by(title=item["title"]).first()

        if not movie:
            movie = Movie(
                title=item["title"],
                description=item["description"]
            )
            db.session.add(movie)

        movie.description = item["description"]
        movie.poster_url = item["poster_url"]
        movie.backdrop_url = item["backdrop_url"] or item["poster_url"]
        movie.language = item["language"]
        movie.genre = item["genre"]
        movie.release_date = item["release_date"]
        movie.rating = item["rating"]
        movie.runtime_minutes = item["runtime_minutes"]
        movie.certificate = item["certificate"]
        movie.cast_names = item["cast_names"]
        movie.director_names = item["director_names"]
        movie.writer_names = item["writer_names"]
        movie.tmdb_url = f"https://www.imdb.com/title/{item['imdb_id']}/" if item["imdb_id"] else ""
        movie.data_source = "imdbapi"

        bookmyshow_links = bookmyshow_links_for_title(item["title"])
        movie.bookmyshow_movie_url = bookmyshow_links["movie"]
        movie.bookmyshow_ticket_url = bookmyshow_links["ticket"]
        movie.bookmyshow_url = bookmyshow_links["primary"]
        movie.justwatch_url = f"https://www.justwatch.com/in/search?q={quote_plus(item['title'])}"

        db.session.flush()

        existing_show = Show.query.filter_by(
            movie_id=movie.id,
            theater_id=theater.id,
            screen_id=screen.id
        ).first()

        show_time = f"{item['release_date'] or str(datetime.utcnow().year) + '-12-31'} 10:00"

        if existing_show:
            existing_show.show_time = show_time
            existing_show.price = 0
            continue

        db.session.add(
            Show(
                movie_id=movie.id,
                theater_id=theater.id,
                screen_id=screen.id,
                show_time=show_time,
                price=0
            )
        )

    db.session.commit()
    return True


def apply_featured_movie_details():
    for title, details in FEATURED_MOVIE_DETAILS.items():
        movie = Movie.query.filter_by(title=title).first()

        if not movie:
            continue

        movie.description = details["description"]
        movie.language = details["language"]
        movie.genre = details["genre"]
        movie.release_date = details["release_date"]
        movie.rating = details["rating"]
        movie.runtime_minutes = movie.runtime_minutes or details.get("runtime_minutes")
        movie.certificate = movie.certificate or details.get("certificate", "UA")
        movie.cast_names = movie.cast_names or details.get("cast_names", "")
        movie.director_names = movie.director_names or details.get("director_names", "")
        movie.writer_names = movie.writer_names or details.get("writer_names", "")
        movie.backdrop_url = movie.backdrop_url or movie.poster_url
        movie.justwatch_url = details["justwatch_url"]
        movie.data_source = "curated"

        bookmyshow_links = bookmyshow_links_for_title(title)
        movie.bookmyshow_movie_url = bookmyshow_links["movie"]
        movie.bookmyshow_ticket_url = bookmyshow_links["ticket"]
        movie.bookmyshow_url = bookmyshow_links["primary"]

    db.session.commit()


def sync_booking_catalog_from_tmdb(force=False):
    settings = SystemSetting.query.first()
    today_key = datetime.utcnow().strftime("%Y-%m-%d")

    if not settings:
        return False

    if not force and settings.tmdb_last_sync == today_key:
        return False

    try:
        tmdb_movies = fetch_booking_catalog_from_tmdb()
    except Exception as error:
        print("TMDb sync failed:", error)
        return False

    if not tmdb_movies:
        return False

    theater_seed = THEATER_NETWORK[:8]

    theaters = []

    for name, city, address, total_screens, *_ in theater_seed:
        theater = Theater.query.filter_by(name=name, city=city).first()

        if not theater:
            theater = Theater(
                name=name,
                city=city,
                address=address,
                total_screens=total_screens
            )
            db.session.add(theater)
            db.session.flush()
        else:
            theater.address = address
            theater.total_screens = total_screens

        for index in range(1, total_screens + 1):
            ensure_screen(theater, f"Screen {index}", 96 + (index * 18))

        theaters.append(theater)

    db.session.flush()

    movies = []

    for item in tmdb_movies:
        movie = Movie.query.filter_by(tmdb_id=item["tmdb_id"]).first()

        if not movie:
            movie = Movie.query.filter_by(title=item["title"]).first()

        if not movie:
            movie = Movie(title=item["title"], description=item["description"])
            db.session.add(movie)

        movie.title = item["title"]
        movie.description = item["description"]
        movie.poster_url = item["poster_url"]
        movie.backdrop_url = item.get("backdrop_url") or item["poster_url"]
        movie.language = item["language"]
        movie.genre = item["genre"]
        movie.release_date = item["release_date"]
        movie.rating = item["rating"]
        movie.tmdb_id = item["tmdb_id"]
        movie.tmdb_url = f"https://www.themoviedb.org/movie/{item['tmdb_id']}"
        movie.data_source = "tmdb"

        encoded_title = quote_plus(item["title"])
        bookmyshow_links = bookmyshow_links_for_title(item["title"])
        movie.bookmyshow_movie_url = bookmyshow_links["movie"]
        movie.bookmyshow_ticket_url = bookmyshow_links["ticket"]
        movie.bookmyshow_url = bookmyshow_links["primary"]
        movie.justwatch_url = f"https://www.justwatch.com/in/search?q={encoded_title}"
        movies.append(movie)

    db.session.flush()

    base_day = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    show_times = ("10:30", "13:45", "17:15", "20:45")
    prices = (180, 220, 260, 320)

    for movie_index, movie in enumerate(movies[:16]):
        for slot_index in range(2):
            theater = theaters[(movie_index + slot_index) % len(theaters)]
            screens = Screen.query.filter_by(theater_id=theater.id).order_by(Screen.id.asc()).all()
            screen = screens[slot_index % len(screens)]
            day = base_day + timedelta(days=movie_index % 5)
            show_time = f"{day.date()} {show_times[(movie_index + slot_index) % len(show_times)]}"

            existing_show = Show.query.filter_by(
                movie_id=movie.id,
                theater_id=theater.id,
                screen_id=screen.id,
                show_time=show_time
            ).first()

            if existing_show:
                existing_show.price = prices[(movie_index + slot_index) % len(prices)]
                continue

            db.session.add(
                Show(
                    movie_id=movie.id,
                    theater_id=theater.id,
                    screen_id=screen.id,
                    show_time=show_time,
                    price=prices[(movie_index + slot_index) % len(prices)]
                )
            )

    settings.tmdb_last_sync = today_key
    db.session.commit()
    return True


