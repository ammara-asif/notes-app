"""Queue access: the API only *puts* jobs here; the worker takes them off.

Redis plays the role that AWS SQS would play in the cloud.
"""
import os

import redis

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
QUEUE_NAME = "notes_queue"

client = redis.Redis.from_url(REDIS_URL)


def enqueue(note_id: int) -> None:
    # LPUSH adds to the left of a list; the worker BRPOPs from the right,
    # so the list behaves as a first-in, first-out queue.
    client.lpush(QUEUE_NAME, note_id)
