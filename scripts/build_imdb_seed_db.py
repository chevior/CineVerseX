import os
import sqlite3
import sys


SOURCE_DB = "cineversex.db"
OUTPUT_DB = os.path.join("backend", "data", "imdb_seed.db")
TARGET_BYTES = 95_000_000
BATCH_SIZE = 5_000


def ensure_schema(connection):
    connection.executescript(
        """
        PRAGMA journal_mode = OFF;
        PRAGMA synchronous = OFF;

        CREATE TABLE IF NOT EXISTS imdb_titles (
            tconst TEXT PRIMARY KEY,
            titleType TEXT,
            primaryTitle TEXT,
            originalTitle TEXT,
            isAdult INTEGER,
            startYear INTEGER,
            runtimeMinutes INTEGER,
            genres TEXT
        );

        CREATE TABLE IF NOT EXISTS imdb_ratings (
            tconst TEXT PRIMARY KEY,
            averageRating REAL,
            numVotes INTEGER
        );

        CREATE INDEX IF NOT EXISTS idx_imdb_titles_type_adult_year
            ON imdb_titles(titleType, isAdult, startYear);
        CREATE INDEX IF NOT EXISTS idx_imdb_titles_primary
            ON imdb_titles(primaryTitle);
        CREATE INDEX IF NOT EXISTS idx_imdb_ratings_votes
            ON imdb_ratings(numVotes);
        """
    )


def seed_rows(source, query, params=()):
    cursor = source.execute(query, params)
    while True:
        rows = cursor.fetchmany(BATCH_SIZE)
        if not rows:
            break
        yield rows


def insert_rows(destination, rows):
    destination.executemany(
        """
        INSERT OR IGNORE INTO imdb_titles (
            tconst,
            titleType,
            primaryTitle,
            originalTitle,
            isAdult,
            startYear,
            runtimeMinutes,
            genres
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                row["tconst"],
                row["titleType"],
                row["primaryTitle"],
                row["originalTitle"],
                row["isAdult"],
                row["startYear"],
                row["runtimeMinutes"],
                row["genres"],
            )
            for row in rows
        ],
    )
    destination.executemany(
        """
        INSERT OR IGNORE INTO imdb_ratings (
            tconst,
            averageRating,
            numVotes
        )
        VALUES (?, ?, ?)
        """,
        [
            (
                row["tconst"],
                row["averageRating"],
                row["numVotes"],
            )
            for row in rows
            if row["averageRating"] is not None or row["numVotes"] is not None
        ],
    )


def current_size(path):
    return os.path.getsize(path) if os.path.exists(path) else 0


def build_seed(source_path=SOURCE_DB, output_path=OUTPUT_DB, target_bytes=TARGET_BYTES):
    if not os.path.exists(source_path):
        raise SystemExit(f"Source database not found: {source_path}")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    if os.path.exists(output_path):
        os.remove(output_path)

    source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    destination = sqlite3.connect(output_path)

    ensure_schema(destination)

    queries = [
        (
            "upcoming and recent Indian/global movies",
            """
            SELECT
                t.tconst,
                t.titleType,
                t.primaryTitle,
                t.originalTitle,
                t.isAdult,
                t.startYear,
                t.runtimeMinutes,
                t.genres,
                r.averageRating,
                r.numVotes
            FROM imdb_titles t
            LEFT JOIN imdb_ratings r ON r.tconst = t.tconst
            WHERE t.titleType = 'movie'
            AND t.isAdult = 0
            AND CAST(t.startYear AS INTEGER) >= 2020
            ORDER BY CAST(t.startYear AS INTEGER) DESC, COALESCE(r.numVotes, 0) DESC
            """,
        ),
        (
            "most voted movies",
            """
            SELECT
                t.tconst,
                t.titleType,
                t.primaryTitle,
                t.originalTitle,
                t.isAdult,
                t.startYear,
                t.runtimeMinutes,
                t.genres,
                r.averageRating,
                r.numVotes
            FROM imdb_ratings r
            JOIN imdb_titles t ON t.tconst = r.tconst
            WHERE t.titleType = 'movie'
            AND t.isAdult = 0
            ORDER BY r.numVotes DESC, r.averageRating DESC
            """,
        ),
        (
            "highest rated movies",
            """
            SELECT
                t.tconst,
                t.titleType,
                t.primaryTitle,
                t.originalTitle,
                t.isAdult,
                t.startYear,
                t.runtimeMinutes,
                t.genres,
                r.averageRating,
                r.numVotes
            FROM imdb_ratings r
            JOIN imdb_titles t ON t.tconst = r.tconst
            WHERE t.titleType = 'movie'
            AND t.isAdult = 0
            AND r.numVotes >= 1000
            ORDER BY r.averageRating DESC, r.numVotes DESC
            """,
        ),
        (
            "remaining movies by newest year",
            """
            SELECT
                t.tconst,
                t.titleType,
                t.primaryTitle,
                t.originalTitle,
                t.isAdult,
                t.startYear,
                t.runtimeMinutes,
                t.genres,
                r.averageRating,
                r.numVotes
            FROM imdb_titles t
            LEFT JOIN imdb_ratings r ON r.tconst = t.tconst
            WHERE t.titleType = 'movie'
            AND t.isAdult = 0
            ORDER BY CAST(t.startYear AS INTEGER) DESC, t.primaryTitle COLLATE NOCASE ASC
            """,
        ),
    ]

    for label, query in queries:
        print(f"Adding {label}...")
        for rows in seed_rows(source, query):
            insert_rows(destination, rows)
            destination.commit()

            if current_size(output_path) >= target_bytes:
                break

        if current_size(output_path) >= target_bytes:
            break

    destination.execute("VACUUM")
    destination.close()
    source.close()

    final_size = current_size(output_path)
    print(f"Created {output_path} ({final_size / (1024 * 1024):.1f} MiB)")


if __name__ == "__main__":
    source = sys.argv[1] if len(sys.argv) > 1 else SOURCE_DB
    output = sys.argv[2] if len(sys.argv) > 2 else OUTPUT_DB
    build_seed(source, output)
