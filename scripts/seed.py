"""Populate the database with a few sample reservations.

Idempotent: it clears existing rows first, so you can re-run it any time to get a
clean demo state.

    docker compose run --rm app python -m scripts.seed
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

from sqlalchemy import text
from sqlmodel import Session

from app.db import engine
from app.reservations import service


def _upcoming_weekday(weekday: int, min_days_ahead: int = 2):
    """The next date landing on `weekday` (Mon=0) that is at least
    `min_days_ahead` days from today — so seeded bookings are never in the past."""
    d = datetime.now().date() + timedelta(days=min_days_ahead)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d


def run() -> None:
    with Session(engine) as session:
        session.exec(text("TRUNCATE reservations, calls RESTART IDENTITY CASCADE"))
        session.commit()

        fri = _upcoming_weekday(4)
        sat = _upcoming_weekday(5)

        samples = [
            # (name, phone, party, date, hour, minute, source, notes)
            ("Ada Lovelace",      "+15550101", 2, fri, 18, 0,  "manual", None),
            ("Alan Turing",       "+15550102", 4, fri, 18, 30, "manual", "window seat if possible"),
            ("Katherine Johnson", "+15550103", 6, fri, 19, 0,  "voice",  "birthday"),
            ("Grace Hopper",      "+15550104", 2, fri, 19, 15, "voice",  None),
            ("Mary Jackson",      "+15550105", 4, fri, 20, 0,  "manual", None),
            ("Dorothy Vaughan",   "+15550106", 3, sat, 17, 30, "manual", None),
            ("Annie Easley",      "+15550107", 5, sat, 18, 0,  "voice",  "anniversary"),
            ("Melba Roy Mouton",  "+15550108", 2, sat, 19, 30, "manual", None),
        ]

        made, skipped = 0, 0
        for name, phone, party, d, hh, mm, src, notes in samples:
            when = datetime.combine(d, time(hh, mm))
            try:
                r = service.create_reservation(
                    session, guest_name=name, phone=phone, party_size=party,
                    when=when, source=src, notes=notes,
                )
                made += 1
                print(f"  {r.confirmation_code}  {name:<20} party {party}  "
                      f"{when:%a %d %b %H:%M}  -> {r.table_id}")
            except service.NoAvailability as e:
                skipped += 1
                print(f"  SKIP {name}: {e.result.reason}")

        print(f"\nseeded {made} reservations ({skipped} skipped)")


if __name__ == "__main__":
    run()
