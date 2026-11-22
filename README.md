# QuickNotes

A tiny but complete **3-tier web app with an async worker**, built to show how a real system fits together.

You type a note and click **Add**. The API saves it as `pending` and puts a job on a queue. A background worker picks up the job, "sends" a notification (about 2s), and marks the note `notified`. The page polls the API, sees the change, and shows a toast: **Note #N saved**.

```
Browser ──HTTP──> nginx  (frontend, localhost:8080)
                    ├─ serves index.html / app.js / style.css
                    └─ /api/*  ──reverse proxy──>  FastAPI (api:8000)
                                                    ├─ INSERT note (pending)  ──> Postgres
                                                    └─ LPUSH note_id          ──> Redis "notes_queue"
Worker (BRPOP loop) <── Redis
   └─ notify (2s) ─> UPDATE status='notified', notified_at ─> Postgres
Browser polls GET /api/notes every 2s while anything is pending
```

| Tier / role | Here | Cloud equivalent (e.g. AWS) |
|---|---|---|
| Presentation | nginx + HTML/JS | S3 + CloudFront / ALB |
| Application | FastAPI | ECS / EC2 / API Gateway + Lambda |
| Data | PostgreSQL | RDS |
| Queue | Redis list | SQS |
| Async worker | Python loop | Lambda triggered by SQS |

## File tour
| File | What it does |
|---|---|
| `frontend/index.html` | The page: input, Add button, notes list, toast area |
| `frontend/app.js` | Calls `/api/notes` (POST to add, GET to list), polls every 2s while a note is pending, shows a toast when pending → notified |
| `frontend/style.css` | Minimal styling |
| `frontend/nginx.conf` | Serves static files and forwards `/api/` to the `api` container (same origin, so no CORS) |
| `frontend/Dockerfile` | nginx:alpine image with the files baked in |
| `api/app/main.py` | FastAPI routes: `GET /api/health`, `GET /api/notes`, `POST /api/notes` (rejects empty text with 422) |
| `api/app/db.py` | All SQL: creates the `notes` table at startup, insert, list |
| `api/app/queue.py` | `enqueue(note_id)` pushes onto the Redis list `notes_queue` |
| `api/tests/test_api.py` | Unit tests with DB and queue faked (used by CI in assignment 2) |
| `worker/worker.py` | Waits on the queue (`BRPOP`), notifies, updates the row; one failed job doesn't stop the loop |
| `docker-compose.yml` | Defines all 5 services, healthchecks, startup order, DB volume |
| `.env.example` | Config (DB credentials, connection URLs). Copy it to `.env` |

## Run it (PowerShell)
```powershell
cd C:\Users\hp\devops\assignment1
Copy-Item .env.example .env        # first time only
docker compose up --build -d
docker compose ps                  # 5 services; db and redis "healthy"
```
Open http://localhost:8080 and add a note.

Stop it with `docker compose down`. To also wipe the database, use `docker compose down -v`.

## Watch the async flow
```powershell
docker compose logs -f worker                                        # see NOTIFY lines appear
docker compose exec redis redis-cli LLEN notes_queue                 # jobs waiting in the queue
docker compose exec db psql -U notes -d notes -c "SELECT * FROM notes;"
curl.exe http://localhost:8080/api/health
curl.exe -X POST -H "Content-Type: application/json" -d '{\"text\":\"from curl\"}' http://localhost:8080/api/notes
```

## Simulate failures
| Try | What happens | Lesson |
|---|---|---|
| `docker compose stop worker`, then add a note | Note stays `pending`; `LLEN notes_queue` = 1 | The API still works: the queue *decouples* the API from the worker |
| `docker compose start worker` | Job is processed, note becomes `notified`, toast appears | Queued work isn't lost |
| `docker compose stop db` | Adding a note fails (500) | The data tier is a single point of failure (in the cloud: Multi-AZ RDS) |
| `docker compose stop api` | Page loads but `/api` returns 502 from nginx | The frontend and API are separate tiers |

## Run tests
```powershell
docker compose run --rm api pytest -q
```

## Deliverables (`docs/`)
| File | What it is |
|---|---|
| `architecture.drawio` | Editable architecture diagram (open in diagrams.net or the VS Code Draw.io extension) |
| `architecture.png` | The same diagram exported as an image |
| `architecture-writeup.md` / `.docx` | Two-page architecture write-up |
| `presentation.pptx` | Two slides: architecture, then request flow + failure tests + AWS mapping |
