"""SQLite database helpers using parameterized '?' SQL queries."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from flask import Flask, current_app, g


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS student (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_number TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    major TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS course (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE COLLATE NOCASE,
    title TEXT NOT NULL,
    credits INTEGER NOT NULL CHECK (credits BETWEEN 1 AND 30),
    capacity INTEGER NOT NULL CHECK (capacity >= 1),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS enrollment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('enrolled', 'completed', 'dropped')),
    grade TEXT CHECK (grade IS NULL OR grade IN ('A', 'B', 'C', 'D', 'E', 'F')),
    enrolled_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (student_id, course_id),
    FOREIGN KEY (student_id) REFERENCES student(id) ON DELETE RESTRICT,
    FOREIGN KEY (course_id) REFERENCES course(id) ON DELETE RESTRICT
);
"""


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_iso_datetime(value: str) -> datetime:
    """Parse an ISO-8601 string stored in SQLite into a timezone-aware datetime."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: str) -> None:
    """Create parent directory if needed and ensure all SQLite tables exist."""
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = _connect(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


def get_db() -> sqlite3.Connection:
    """Get or open the request-scoped SQLite connection with foreign keys enabled."""
    if "_db" not in g:
        g._db = _connect(current_app.config["DATABASE_PATH"])
    return g._db


def close_db(_exc: BaseException | None = None) -> None:
    """Close the request-scoped SQLite connection on teardown."""
    conn: sqlite3.Connection | None = g.pop("_db", None)
    if conn is not None:
        conn.close()


def init_app(app: Flask) -> None:
    """Initialize SQLite schema and register request teardown hook."""
    init_db(app.config["DATABASE_PATH"])
    app.teardown_appcontext(close_db)


def student_row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "student_number": row["student_number"],
        "name": row["name"],
        "email": row["email"],
        "major": row["major"],
        "created_at": parse_iso_datetime(row["created_at"]),
    }


def course_row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "code": row["code"],
        "title": row["title"],
        "credits": row["credits"],
        "capacity": row["capacity"],
        "enrolled_count": row["enrolled_count"],
        "created_at": parse_iso_datetime(row["created_at"]),
    }


def enrollment_row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "student_id": row["student_id"],
        "course_id": row["course_id"],
        "status": row["status"],
        "grade": row["grade"],
        "enrolled_at": parse_iso_datetime(row["enrolled_at"]),
        "updated_at": parse_iso_datetime(row["updated_at"]),
    }
