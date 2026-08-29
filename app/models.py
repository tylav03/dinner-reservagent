"""Database tables (SQLModel = SQLAlchemy 2.x core + Pydantic).

Design notes
------------
* The physical table inventory (T1..T14 and their capacities) is *not* a database
  table. It lives in `restaurant_config.py` so there is exactly one source of
  truth for a single hard-coded venue. `Reservation.table_id` is just a string
  that matches a config id; there is no foreign key. If tables ever need to be
  editable at runtime, promote them to a real table then.

* Booking times are stored as **naive local datetimes** (`start_at`, `end_at`) in
  the restaurant's timezone, matching the availability engine. Overlap queries
  become simple range comparisons on `start_at` / `end_at`.

* `created_at` / `updated_at` are audit stamps in server local time.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Index, UniqueConstraint
from sqlmodel import Field, SQLModel

# --- reservation status ---------------------------------------------------
STATUS_BOOKED = "booked"
STATUS_SEATED = "seated"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"
STATUS_NO_SHOW = "no_show"

# --- how a reservation was created --------------------------------------
SOURCE_VOICE = "voice"
SOURCE_MANUAL = "manual"
SOURCE_API = "api"

# --- how a phone call ended -------------------------------------------
DISPOSITION_BOOKED = "booked"
DISPOSITION_NO_AVAILABILITY = "no_availability"
DISPOSITION_ABANDONED = "abandoned"
DISPOSITION_TRANSFERRED = "transferred"
DISPOSITION_ERROR = "error"


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now()


class Reservation(SQLModel, table=True):
    __tablename__ = "reservations"
    __table_args__ = (
        # Idempotency: a retried create with the same key must not double-book.
        UniqueConstraint("idempotency_key", name="uq_reservations_idempotency_key"),
        # Backstop against a double-booked table. The real guard is row locking
        # in service.create_reservation; this catches anything that slips past.
        Index(
            "uq_reservations_table_slot",
            "table_id",
            "start_at",
            unique=True,
            postgresql_where="status = 'booked'",
        ),
        Index("ix_reservations_start_at", "start_at"),
    )

    id: str = Field(default_factory=_uuid, primary_key=True)
    confirmation_code: str = Field(index=True, unique=True)

    guest_name: str
    phone: str
    party_size: int

    start_at: datetime
    end_at: datetime
    table_id: str | None = None

    status: str = STATUS_BOOKED
    source: str = SOURCE_MANUAL
    notes: str | None = None

    idempotency_key: str | None = Field(default=None)

    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class Call(SQLModel, table=True):
    """One inbound phone call. Populated in Phase 5; defined now so the schema is
    stable."""

    __tablename__ = "calls"

    id: str = Field(default_factory=_uuid, primary_key=True)
    twilio_call_sid: str = Field(index=True, unique=True)
    from_number: str | None = None

    started_at: datetime = Field(default_factory=_now)
    ended_at: datetime | None = None
    duration_seconds: int | None = None

    disposition: str | None = None
    reservation_id: str | None = Field(default=None, foreign_key="reservations.id")

    recording_path: str | None = None
    transcript_json: str | None = None   # JSON-encoded list of turns
    metrics_json: str | None = None      # JSON-encoded latency / token / cost summary
