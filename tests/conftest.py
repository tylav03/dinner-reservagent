"""Shared test fixtures.

Two tiers of tests:

* **Pure logic** (`test_availability.py`) — imports only the availability engine
  and the restaurant config. Needs no database and no fixtures here. Runs
  anywhere: `pytest tests/test_availability.py`.

* **DB-backed** (`test_service.py`, `test_concurrency.py`, `test_api.py`) — use
  the `session` / `client` fixtures below, which require a running Postgres.
  Start one first:

      docker compose up -d db          # then: pytest

  These tests use a dedicated `*_test` database (the app's DATABASE_URL with
  `_test` appended) so they never touch dev data.

Nothing here is `autouse`, so importing this file never opens a connection.
"""

from __future__ import annotations

import os

import psycopg
import pytest
from dotenv import load_dotenv
from sqlalchemy.engine import make_url

# Load .env so host runs pick up DATABASE_URL (localhost:5433). Inside the compose
# network the env var is already set to the "db" host. Setting an env var opens
# no connection, so this is safe for pure-logic tests too.
load_dotenv()

_raw = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://postgres:postgres@db:5432/reservations"
)
if not make_url(_raw).database.endswith("_test"):
    _raw = _raw + "_test"
os.environ["DATABASE_URL"] = _raw
_URL = make_url(_raw)


def _ensure_database() -> None:
    try:
        admin = psycopg.connect(
            host=_URL.host, port=_URL.port or 5432,
            user=_URL.username, password=_URL.password, dbname="postgres",
            autocommit=True, connect_timeout=3,
        )
    except psycopg.OperationalError as e:
        pytest.fail(
            f"cannot reach Postgres at {_URL.host}:{_URL.port} for DB-backed tests.\n"
            f"Start it with:  docker compose up -d db\n"
            f"(original error: {e})",
            pytrace=False,
        )
    try:
        exists = admin.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (_URL.database,)
        ).fetchone()
        if not exists:
            admin.execute(f'CREATE DATABASE "{_URL.database}"')
    finally:
        admin.close()


@pytest.fixture(scope="session")
def _database():
    _ensure_database()
    from app.db import create_all, engine

    create_all()
    yield
    engine.dispose()


@pytest.fixture
def _clean_tables(_database):
    """Empty tables before each DB-backed test."""
    from sqlalchemy import text

    from app.db import engine

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE reservations, calls RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def session(_clean_tables):
    from sqlmodel import Session

    from app.db import engine

    with Session(engine) as s:
        yield s


@pytest.fixture
def client(_clean_tables):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c
