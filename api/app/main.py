"""Application tier: a small REST API.

POST /api/notes does two quick things and returns immediately:
  1. saves the note in Postgres with status 'pending'
  2. drops a job on the Redis queue
The slow part (sending the notification) happens later in the worker,
so the user never waits for it. That is the whole point of async processing.
"""
import os
from contextlib import asynccontextmanager
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, field_validator, model_validator

from . import db, queue

Color = Literal["default", "butter", "mint", "sky", "lilac", "rose"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()  # make sure the table exists before serving requests
    yield


app = FastAPI(title="QuickNotes API", lifespan=lifespan)


def _strip(v):
    return v.strip() if isinstance(v, str) else v


class NoteIn(BaseModel):
    title: str = ""
    text: str = ""
    color: Color = "default"

    @field_validator("title", "text")
    @classmethod
    def strip_spaces(cls, v):
        return _strip(v)

    # A note needs a title or a body; FastAPI turns this into a 422 response.
    @model_validator(mode="after")
    def not_empty(self):
        if not self.title and not self.text:
            raise ValueError("note must have a title or text")
        return self


class NoteUpdate(BaseModel):
    title: Optional[str] = None
    text: Optional[str] = None
    color: Optional[Color] = None
    pinned: Optional[bool] = None

    @field_validator("title", "text")
    @classmethod
    def strip_spaces(cls, v):
        return _strip(v)


@app.get("/api/health")
def health():
    # Used by humans, load balancers and CI to check the API is up.
    return {"status": "ok"}


@app.get("/api/version")
def version():
    # Set by the CI/CD pipeline at deploy time, so the live site shows which build it runs.
    return {
        "version": os.environ.get("APP_VERSION", "dev"),
        "commit": os.environ.get("GIT_SHA", "local"),
    }


@app.get("/api/notes")
def get_notes():
    return db.list_notes()


@app.post("/api/notes", status_code=201)
def add_note(note: NoteIn):
    row = db.create_note(note.title, note.text, note.color)
    queue.enqueue(row["id"])
    return row


@app.patch("/api/notes/{note_id}")
def edit_note(note_id: int, changes: NoteUpdate):
    fields = changes.model_dump(exclude_unset=True, exclude_none=True)
    current = db.get_note(note_id)
    if current is None:
        raise HTTPException(status_code=404, detail="note not found")
    # Same rule as creating: an edit can't leave the note with no title and no text.
    merged = {**current, **fields}
    if not merged.get("title") and not merged.get("text"):
        raise HTTPException(status_code=422, detail="note must have a title or text")
    row = db.update_note(note_id, fields)
    if row is None:
        raise HTTPException(status_code=404, detail="note not found")
    return row


@app.delete("/api/notes/{note_id}", status_code=204)
def remove_note(note_id: int):
    if not db.delete_note(note_id):
        raise HTTPException(status_code=404, detail="note not found")
    return Response(status_code=204)
