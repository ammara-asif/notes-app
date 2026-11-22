"""Async worker: takes jobs off the queue and does the slow work.

In the cloud this would be a Lambda function triggered by SQS.
Here it's a plain loop: wait for a job -> notify -> update the database.
"""
import os
import time

import psycopg
import redis

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ["REDIS_URL"]
QUEUE_NAME = "notes_queue"


def send_notification(note_id: int, text: str) -> None:
    # Pretend this is a slow call to an email/SMS/push service.
    time.sleep(2)
    print(f'NOTIFY: "Your note #{note_id} was saved" ({text[:30]!r})')


def handle(note_id: int) -> None:
    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute("SELECT text FROM notes WHERE id = %s", (note_id,)).fetchone()
    if row is None:
        print(f"note {note_id} not found, skipping")
        return

    # Do the slow external call *outside* any DB transaction, so we don't hold
    # a database transaction open while waiting on another service.
    send_notification(note_id, row[0])

    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            "UPDATE notes SET status = 'notified', notified_at = now() WHERE id = %s",
            (note_id,),
        )


def main() -> None:
    r = redis.Redis.from_url(REDIS_URL)
    print("worker started, waiting for jobs...")
    while True:
        # BRPOP blocks until a job arrives (no busy polling).
        _, raw_id = r.brpop(QUEUE_NAME)
        try:
            handle(int(raw_id))
        except Exception as e:
            # One bad job must not crash the worker; log it and move on.
            print(f"job {raw_id!r} failed: {e}")


if __name__ == "__main__":
    main()
