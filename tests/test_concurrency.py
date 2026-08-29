"""The double-booking race.

Two threads try to book the *last* available table for the same slot at the same
moment. Exactly one must succeed; the other must get a clean NoAvailability.

This is the test that proves the `pg_advisory_xact_lock` + partial-unique-index
guard in `service.create_reservation` actually works. Needs a real Postgres
(SQLite has no such locking), so it runs in Docker.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta

from sqlmodel import Session

from app.db import engine
from app.reservations import service
from app.restaurant_config import CONFIG


def _future_saturday_6pm() -> datetime:
    d = datetime.now().date()
    while d.weekday() != 5:
        d += timedelta(days=1)
    d += timedelta(days=7)
    return datetime(d.year, d.month, d.day, 18, 0)


def test_only_one_of_two_concurrent_bookings_wins(session):
    when = _future_saturday_6pm()

    # Fill every table except one 2-top, so there is exactly one seat left.
    two_tops = [t.id for t in CONFIG.tables if t.capacity == 2]
    other_tables = [t for t in CONFIG.tables if t.id not in two_tops[:1]]
    for i, t in enumerate(other_tables):
        service.create_reservation(
            session, guest_name=f"seed{i}", phone=str(i),
            party_size=t.capacity, when=when,
        )

    results: list[str] = []
    errors: list[Exception] = []
    barrier = threading.Barrier(2)

    def attempt(tag: str) -> None:
        barrier.wait()  # line both threads up on the DB call
        try:
            with Session(engine) as s:
                r = service.create_reservation(
                    s, guest_name=tag, phone=tag, party_size=2, when=when,
                )
            results.append(r.confirmation_code)
        except service.NoAvailability:
            errors.append(RuntimeError(f"{tag}: no availability"))
        except Exception as e:  # pragma: no cover - surfaces unexpected failures
            errors.append(e)

    threads = [threading.Thread(target=attempt, args=(f"racer{i}",)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert len(results) == 1, f"expected exactly one winner, got {results} / {errors}"
    assert len(errors) == 1
    assert "no availability" in str(errors[0])

    # And the database holds exactly one booking on that last table.
    from sqlmodel import select

    from app.models import Reservation

    booked = session.exec(
        select(Reservation).where(
            Reservation.start_at == when, Reservation.status == "booked",
            Reservation.table_id == two_tops[0],
        )
    ).all()
    assert len(booked) == 1
