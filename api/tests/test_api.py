"""Unit tests for the API. They fake the DB and queue, so no Postgres/Redis is needed.
This is what the CI pipeline (assignment 2) will run.
"""
import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def client(monkeypatch):
    enqueued = []
    monkeypatch.setattr(main.db, "init_db", lambda: None)
    monkeypatch.setattr(main.db, "list_notes", lambda: [])
    monkeypatch.setattr(
        main.db, "create_note", lambda text: {"id": 1, "text": text, "status": "pending"}
    )
    monkeypatch.setattr(main.queue, "enqueue", enqueued.append)
    with TestClient(main.app) as c:
        c.enqueued = enqueued
        yield c


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_empty_note_rejected(client):
    assert client.post("/api/notes", json={"text": "   "}).status_code == 422
    assert client.enqueued == []


def test_create_note_enqueues_job(client):
    r = client.post("/api/notes", json={"text": "hello"})
    assert r.status_code == 201
    assert r.json()["status"] == "pending"
    assert client.enqueued == [1]
