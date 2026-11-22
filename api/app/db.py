"""Data tier access: every SQL statement the API runs lives here.

We use plain SQL (no ORM) so you can see exactly what hits the database.
"""
import os

import psycopg
from psycopg.rows import dict_row

# The connection string comes from the environment (set in .env / docker-compose),
# so the same code works on a laptop, in CI, or in the cloud.
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://notes:notes@localhost:5432/notes")


def get_conn():
    # A new short-lived connection per request keeps things simple.
    # (A real app would use a connection pool.)
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_db():
    """Create the table if it doesn't exist yet. Runs once when the API starts."""
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id          SERIAL PRIMARY KEY,
                text        TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'pending',  -- pending -> notified
                notified_at TIMESTAMPTZ,                      -- set by the worker
                created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )


def create_note(text: str) -> dict:
    with get_conn() as conn:
        return conn.execute(
            "INSERT INTO notes (text) VALUES (%s) RETURNING *", (text,)
        ).fetchone()


def list_notes() -> list[dict]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM notes ORDER BY id DESC").fetchall()
