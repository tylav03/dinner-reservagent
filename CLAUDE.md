# CLAUDE.md

Guidance for working in this repo. See [README.md](README.md) for what the
project is, how to set it up, and the phase roadmap — this file is about
conventions and gotchas that aren't obvious from reading the code cold.

## Running things

- **Always invoke scripts/tests as modules from the project root**
  (`python -m scripts.seed`, `python -m pytest`, `python -m scripts.text_agent`),
  never as a bare file path (`python scripts/seed.py`). A bare path puts the
  script's own directory on `sys.path` instead of the project root, so
  `from app... import ...` fails with `ModuleNotFoundError`.
- **Migration order matters.** Bring up Postgres alone (`docker compose up -d db`),
  run `alembic upgrade head`, *then* bring up the full stack
  (`docker compose up -d`). The API creates tables itself on startup as a
  local-dev convenience (`app/main.py`'s lifespan calls `create_all()`), with
  no `alembic_version` bookkeeping — migrating after the API's already up
  causes `DuplicateTable`.
- **Postgres is on host port 5433, not 5432** — this avoids colliding with a
  Postgres that may already be running on the dev machine's default port.
  Containers still reach it as `db:5432`.
- Pure-logic tests (`test_availability.py`, `test_prompts.py`) need no
  database and run anywhere. Anything using the `session` fixture needs
  `docker compose up -d db` first — see `tests/conftest.py` for how the
  dedicated `*_test` database gets created.
- If the project folder is ever renamed/moved, recreate `.venv` — its console
  scripts (`pytest`, `alembic`) have the old absolute path baked into their
  shebang lines and will silently break.

## Architecture — read before changing the reservation logic

- **`app/reservations/availability.py` is pure** — no DB, no framework, just
  functions of `(datetime, party size, list of existing bookings)`. Keep it
  that way; all persistence/transaction logic belongs in `service.py`.
- **`service.py` is the only thing that talks to Postgres for reservations.**
  Both `router.py` (REST, used by the dashboard) and `app/voice/tools.py`
  (used by the agent) call into `service.py` directly — they never call each
  other. The agent deliberately never goes through HTTP.
- **Double-booking guard**: `pg_advisory_xact_lock` keyed per calendar day is
  the real guard — it serializes same-day writers so the second transaction
  can't even read until the first commits. A partial unique index
  (`table_id, start_at) WHERE status='booked'`) is a belt-and-braces DB-level
  backstop. Row-level `FOR UPDATE` in `_bookings_overlapping` predates the
  advisory lock and is largely vestigial now — don't remove it, but don't
  treat it as the thing doing the work either. Full reasoning is in
  `service.create_reservation`'s docstring.
- **One restaurant, one config.** Every fact about the venue — hours, tables,
  turn time, max party size, timezone — lives in `app/restaurant_config.py`'s
  `CONFIG`. Never hardcode a restaurant fact anywhere else; the agent's
  system prompt is built dynamically from `CONFIG` for exactly this reason
  (see `app/voice/prompts.py`).
- **Time is naive local, always.** The whole app models booking times as
  naive datetimes in the restaurant's timezone — no `tzinfo`. Use
  `restaurant_config.now_local()` for any past/future decision, never
  `datetime.now()` directly. The process may run in UTC (Docker), and using
  the wrong "now" is a real bug that shipped once already (same-day evening
  bookings got wrongly rejected as "past" because the container's clock was
  4+ hours ahead of the restaurant's).
- **Status/source are constants, not string literals** — `STATUS_*` /
  `SOURCE_*` in `app/models.py`. Import and use them; don't retype `"booked"`.
- **"Upcoming" has two slightly different definitions** in this codebase:
  `list_reservations(upcoming_only=...)` uses `start_at >= now` (hasn't
  started); the dashboard and `find_by_phone` use `end_at > now` (hasn't
  finished). The latter is more correct for "is this still relevant" — an
  in-progress reservation should count as current. Know which one you're
  touching.

## The agent (`app/voice/`)

- **Nothing may raise past `call_tool()`.** A live phone call can't recover
  from a crashed tool handler — domain failures, bad arguments, and unknown
  tool names all become a plain `{"error": ...}` dict, never an exception.
- Tool descriptions in `tools.py` aren't just documentation — the model
  reads them to decide what to call and how to talk about the result. When a
  tool returns a coded field (e.g. `reason: "closed"` vs `"full"`), spell out
  in the description what each value means and how to phrase it; don't
  assume the model will infer it correctly (it didn't, once — see PR #6).
- The model will happily reason about things (opening hours, whether a time
  "sounds" available) using only the plain-English facts in the system
  prompt instead of calling a tool. That reasoning is unreliable — it can't
  replicate turn-time math, for instance. The prompt explicitly forbids this
  ("never decide yourself... this tool is the only source of truth") for
  exactly that reason; keep that instruction if you touch the prompt.
- Phase 3 tests conversation quality by literally running
  `python -m scripts.text_agent` and reading the transcript, then writing a
  regression test once a bug is found and fixed — there's no automated
  conversation-quality suite yet (a scripted-scenario eval harness was
  discussed as a good Phase 7 candidate, not yet built). Throwaway
  verification scripts against the real API belong in the scratchpad
  directory, not the repo — they cost real money and aren't deterministic
  enough for the permanent test suite.

## Testing conventions

- Every `service.py` function and every voice tool handler should have a
  test. This repo has twice shipped a real bug through a function with zero
  coverage (`patch_reservation`'s logic, `find_by_phone`'s missing time
  filter) — when adding a new one, add its test in the same change.
- SQLAlchemy's identity map: within one `Session`, fetching the same row
  twice returns the *same Python object*. If a test needs to compare a field
  before and after a mutation, capture the "before" value into a separate
  variable first — comparing against the original reference after mutating
  it is comparing a value to itself. This has produced a silently-useless
  passing test more than once.
- Multi-day/near-midnight and timezone edge cases deserve their own test,
  not just a happy-path one — both real bugs so far (`is_within_hours`'
  midnight-crossing bug, the UTC-vs-restaurant-local `now()` bug) were in
  that category.

## Workflow

- This repo uses GitHub Issues for known-but-not-yet-fixed bugs (`gh issue
  list`) — check there before assuming something is undocumented. Branch →
  PR → `Fixes #N` in the PR body → merge → delete branch is the established
  flow; `gh` is installed and authenticated for this.
- The user prefers to drive git/GitHub Desktop himself — explain steps
  rather than running commit/push for him unless he's explicitly asked for
  that in the moment.
