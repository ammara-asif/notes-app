"""Data tier access: every SQL statement the API runs lives here.

We use plain SQL (no ORM) so you can see exactly what hits the database.
"""
import os

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

# The connection string comes from the environment (set in .env / docker-compose),
# so the same code works on a laptop, in CI, or in the cloud.
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://notes:notes@localhost:5432/notes")

# Columns a client is allowed to change through update_note().
UPDATABLE = {"title", "text", "color", "pinned"}


def get_conn():
    # A new short-lived connection per request keeps things simple.
    # (A real app would use a connection pool.)
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_db():
    """Create the table if needed, then add newer columns. Runs once when the API starts.

    The ALTERs use IF NOT EXISTS so they are safe on a database that was created
    by an older version of the app (e.g. the persistent volume on the server).
    """
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
        conn.execute("ALTER TABLE notes ADD COLUMN IF NOT EXISTS title TEXT NOT NULL DEFAULT ''")
        conn.execute("ALTER TABLE notes ADD COLUMN IF NOT EXISTS color TEXT NOT NULL DEFAULT 'default'")
        conn.execute("ALTER TABLE notes ADD COLUMN IF NOT EXISTS pinned BOOLEAN NOT NULL DEFAULT false")
        conn.execute(
            "ALTER TABLE notes ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
        )


def create_note(title: str, text: str, color: str) -> dict:
    with get_conn() as conn:
        return conn.execute(
            "INSERT INTO notes (title, text, color) VALUES (%s, %s, %s) RETURNING *",
            (title, text, color),
        ).fetchone()


def list_notes() -> list[dict]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM notes ORDER BY pinned DESC, id DESC").fetchall()


def get_note(note_id: int) -> dict | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM notes WHERE id = %s", (note_id,)).fetchone()


def update_note(note_id: int, fields: dict) -> dict | None:
    """Change only the given fields. Returns the updated row, or None if it doesn't exist."""
    fields = {k: v for k, v in fields.items() if k in UPDATABLE}
    assignments = [sql.SQL("{} = %s").format(sql.Identifier(k)) for k in fields]
    assignments.append(sql.SQL("updated_at = now()"))
    query = sql.SQL("UPDATE notes SET {} WHERE id = %s RETURNING *").format(
        sql.SQL(", ").join(assignments)
    )
    with get_conn() as conn:
        return conn.execute(query, (*fields.values(), note_id)).fetchone()


def delete_note(note_id: int) -> bool:
    with get_conn() as conn:
        return conn.execute("DELETE FROM notes WHERE id = %s", (note_id,)).rowcount > 0
