# AI Voice Reservation Agent

An AI agent that answers a restaurant's phone, has a natural conversation with
the caller, and books a table — checked against a real availability system so
it never double-books. This repo is the reservation system the agent (and a
staff-facing dashboard) both run on.

**Status: in active development.** The reservation backend and the staff
dashboard are built and working end to end. The voice agent itself (phone
call → LLM → booking) is the next phase — see [Roadmap](#roadmap).

## What's here today

- **A transactional reservation API** (Python/FastAPI/PostgreSQL) with a pure
  availability engine — opening hours, table turn times, greedy table
  assignment — wrapped by a service layer that prevents double-booking races
  with a per-day Postgres advisory lock and a partial unique index.
- **A staff dashboard** (React/TypeScript/Tailwind): a date-scoped reservation
  list with history, a floor-plan timeline view, and a booking form built
  around an availability-first "openings strip" so a host sees what's actually
  bookable before they try.
- **50 passing tests** covering the availability engine, the transactional
  layer (including a real concurrency test), and the HTTP API.

## Architecture

```
 Caller's phone  ──(planned)──▶  Twilio  ──▶  Pipecat + OpenAI Realtime API
                                                        │ tool calls
                                                        ▼
                                          ┌─────────────────────────┐
                                          │   FastAPI backend        │
                                          │   (this repo, app/)      │
                                          │                          │
 Staff dashboard  ───────HTTP───────────▶│  availability engine  ───┼──▶ PostgreSQL
 (frontend/)                             │  booking service         │
                                          └─────────────────────────┘
```

The voice agent and the staff dashboard are meant to hit the **same**
availability logic — a booking made by phone and one made by a host at the
front desk are checked, and can conflict with, each other identically.

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python, FastAPI, SQLModel, Alembic |
| Database | PostgreSQL |
| Frontend | React, TypeScript, Vite, Tailwind CSS v4 |
| Voice (planned) | Twilio, [Pipecat](https://github.com/pipecat-ai/pipecat), OpenAI Realtime API |
| Dev environment | Docker Compose |

## Getting started

Requires Docker, Python 3.12+, and Node 20+.

```bash
git clone https://github.com/tylav03/dinner-reservagent.git
cd dinner-reservagent
cp .env.example .env

# Postgres (:5433 on the host — see note below) + the API (:8000)
docker compose up -d

# apply migrations and load sample data
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
python -m scripts.seed

# frontend, in a second terminal
cd frontend
cp .env.example .env.local
npm install
npm run dev   # http://localhost:5173
```

> **Port 5433, not 5432:** the Postgres container is deliberately published on
> `5433` so it doesn't collide with a Postgres already running on your machine
> on the default port. Inside Docker's network other containers still reach it
> as `db:5432`.

## Testing

```bash
docker compose up -d db
pytest                       # 50 tests: engine, service/concurrency, API

cd frontend
npx tsc -b && npm run build  # typecheck + production build
```

## Project structure

```
app/
├── main.py                    FastAPI app
├── models.py                  SQLModel tables
├── restaurant_config.py       venue config: hours, tables, turn time, timezone
└── reservations/
    ├── availability.py        pure conflict/availability engine (no DB)
    ├── service.py              transactional booking, concurrency guard
    ├── router.py                REST endpoints
    └── schemas.py                request/response models
frontend/src/
├── App.tsx                    date-scoped viewer shell
├── components/
│   ├── ReservationsList.tsx   list + history toggle
│   ├── DayTimeline.tsx        floor-plan view
│   ├── NewReservationForm.tsx booking form
│   ├── OpeningsStrip.tsx      availability heatmap
│   └── Toast.tsx              confirmation toasts
└── hooks.ts / api.ts / lib/    data fetching + helpers
tests/                         pytest suite
scripts/seed.py                rolling demo data (recent past → next week)
alembic/                       schema migrations
```

## Roadmap

- [x] **Phase 1** — reservation core: availability engine, transactional
      booking, REST API, migrations
- [x] **Phase 2** — staff dashboard: reservation viewer, floor plan, booking
      form, availability strip
- [ ] **Phase 3** — text-mode agent: tool-calling logic against this API,
      driven from a terminal chat (no audio yet)
- [ ] **Phase 4** — local voice loop: browser mic ↔ OpenAI Realtime API
- [ ] **Phase 5** — telephony: Twilio number + Media Streams, call recording
- [ ] **Phase 6** — deployment: self-hosted VPS, Docker Compose, HTTPS
- [ ] **Phase 7** — evaluation harness + polish

## License

GPL-3.0 — see [LICENSE](LICENSE).
