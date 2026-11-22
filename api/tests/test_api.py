"""Unit tests for the API. They fake the DB and queue, so no Postgres/Redis is needed.
This is what the CI pipeline runs before anything gets deployed.
"""
import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def client(monkeypatch):
    enqueued = []
    store = {1: {"id": 1, "title": "", "text": "existing", "color": "default", "pinned": False}}

    def create_note(title, text, color):
        return {"id": 2, "title": title, "text": text, "color": color, "status": "pending"}

    def update_note(note_id, fields):
        if note_id not in store:
            return None
        store[note_id].update(fields)
        return store[note_id]

    monkeypatch.setattr(main.db, "init_db", lambda: None)
    monkeypatch.setattr(main.db, "list_notes", lambda: list(store.values()))
    monkeypatch.setattr(main.db, "create_note", create_note)
    monkeypatch.setattr(main.db, "get_note", lambda note_id: store.get(note_id))
    monkeypatch.setattr(main.db, "update_note", update_note)
    monkeypatch.setattr(main.db, "delete_note", lambda note_id: store.pop(note_id, None) is not None)
    monkeypatch.setattr(main.queue, "enqueue", enqueued.append)
    with TestClient(main.app) as c:
        c.enqueued = enqueued
        yield c


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_version_defaults(client, monkeypatch):
    monkeypatch.delenv("APP_VERSION", raising=False)
    monkeypatch.delenv("GIT_SHA", raising=False)
    assert client.get("/api/version").json() == {"version": "dev", "commit": "local"}


def test_version_from_env(client, monkeypatch):
    monkeypatch.setenv("APP_VERSION", "42")
    monkeypatch.setenv("GIT_SHA", "abc1234")
    assert client.get("/api/version").json() == {"version": "42", "commit": "abc1234"}


def test_empty_note_rejected(client):
    assert client.post("/api/notes", json={"title": "  ", "text": "   "}).status_code == 422
    assert client.enqueued == []


def test_create_note_enqueues_job(client):
    r = client.post("/api/notes", json={"text": "hello"})
    assert r.status_code == 201
    assert r.json()["status"] == "pending"
    assert client.enqueued == [2]


def test_create_note_with_title_and_color(client):
    r = client.post("/api/notes", json={"title": " Groceries ", "text": "", "color": "mint"})
    assert r.status_code == 201
    assert r.json()["title"] == "Groceries"
    assert r.json()["color"] == "mint"


def test_invalid_color_rejected(client):
    assert client.post("/api/notes", json={"text": "x", "color": "neon"}).status_code == 422


def test_patch_note(client):
    r = client.patch("/api/notes/1", json={"pinned": True, "color": "sky"})
    assert r.status_code == 200
    assert r.json()["pinned"] is True
    assert r.json()["color"] == "sky"
    assert r.json()["text"] == "existing"  # untouched fields stay the same


def test_patch_edits_title_and_text(client):
    r = client.patch("/api/notes/1", json={"title": " Plans ", "text": "new body"})
    assert r.status_code == 200
    assert r.json()["title"] == "Plans"
    assert r.json()["text"] == "new body"


def test_patch_cannot_empty_note(client):
    # Note 1 has no title, so clearing its text would leave it empty.
    assert client.patch("/api/notes/1", json={"text": "   "}).status_code == 422
    assert client.patch("/api/notes/1", json={"title": "", "text": ""}).status_code == 422
    assert client.get("/api/notes").json()[0]["text"] == "existing"


def test_patch_invalid_color_rejected(client):
    assert client.patch("/api/notes/1", json={"color": "neon"}).status_code == 422


def test_patch_missing_note(client):
    assert client.patch("/api/notes/999", json={"pinned": True}).status_code == 404


def test_delete_note(client):
    assert client.delete("/api/notes/1").status_code == 204
    assert client.get("/api/notes").json() == []


def test_delete_missing_note(client):
    assert client.delete("/api/notes/999").status_code == 404
