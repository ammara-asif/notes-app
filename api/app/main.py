"""Application tier: a tiny REST API.

POST /api/notes does two quick things and returns immediately:
  1. saves the note in Postgres with status 'pending'
  2. drops a job on the Redis queue
The slow part (sending the notification) happens later in the worker,
so the user never waits for it. That is the whole point of async processing.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel, field_validator

from . import db, queue


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()  # make sure the table exists before serving requests
    yield


app = FastAPI(title="QuickNotes API", lifespan=lifespan)


class NoteIn(BaseModel):
    text: str

    # Reject empty / whitespace-only notes; FastAPI turns this into a 422 response.
    @field_validator("text")
    @classmethod
    def not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("text must not be empty")
        return v


@app.get("/api/health")
def health():
    # Used by humans, load balancers and CI to check the API is up.
    return {"status": "ok"}


@app.get("/api/notes")
def get_notes():
    return db.list_notes()


@app.post("/api/notes", status_code=201)
def add_note(note: NoteIn):
    row = db.create_note(note.text)
    queue.enqueue(row["id"])
    return row
