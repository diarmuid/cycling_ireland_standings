"""Database setup and helpers for the Cycling Ireland Rankings scraper."""

import sqlite3
from pathlib import Path

from config import DB_PATH


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """Return a connection to the SQLite database with row factory enabled."""
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection | None = None) -> sqlite3.Connection:
    """Create tables if they don't exist and return the connection."""
    close = conn is None
    conn = conn or get_connection()

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS riders (
            uuid TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            club TEXT,
            gender TEXT
        );

        CREATE TABLE IF NOT EXISTS rankings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rider_uuid TEXT NOT NULL REFERENCES riders(uuid),
            competition_category TEXT NOT NULL,
            rider_category TEXT,
            rank INTEGER NOT NULL,
            points TEXT,
            is_provisional INTEGER DEFAULT 0,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS race_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rider_uuid TEXT NOT NULL REFERENCES riders(uuid),
            event_name TEXT,
            race_name TEXT,
            position TEXT,
            points TEXT,
            race_date TEXT,
            year INTEGER,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS scrape_meta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            rider_count INTEGER,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_rankings_category_rank
            ON rankings(competition_category, rank);

        CREATE INDEX IF NOT EXISTS idx_rankings_rider
            ON rankings(rider_uuid);

        CREATE INDEX IF NOT EXISTS idx_race_results_rider
            ON race_results(rider_uuid);
    """)

    if close:
        conn.close()
    return conn