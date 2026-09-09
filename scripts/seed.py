"""Populate the database with sample reservations for a live demo.

Seeds a rolling window: today (including some slots that have already passed, so
the "Show history" UI has content) plus the next 7 open days. Idempotent — clears
existing rows first, so re-run any time for a fresh state:

    docker compose run --rm app python -m scripts.seed
    # or, from the host venv:  python -m scripts.seed

Note: to control the past/future mix precisely, rows are inserted directly via the
ORM rather than through `service.create_reservation` (which refuses past times).
Table assignment still goes through the real availability engine so seeded
bookings never overlap.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlmodel import Session

from app.db import engine
from app.models import (
    STATUS_BOOKED,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_NO_SHOW,
    Reservation,
)
from app.reservations.availability import Booking, assign_table
from app.reservations.service import _generate_code
from app.restaurant_config import CONFIG

# Phone numbers use the 555-01xx range (reserved for fictional use) with real
# US area codes, so they're a full 10 digits and clearly not anyone's line.
GUESTS = [
    ("Ada Lovelace", "(415) 555-0101"),
    ("Alan Turing", "(415) 555-0102"),
    ("Katherine Johnson", "(628) 555-0103"),
    ("Grace Hopper", "(628) 555-0104"),
    ("Mary Jackson", "(510) 555-0105"),
    ("Dorothy Vaughan", "(510) 555-0106"),
    ("Annie Easley", "(650) 555-0107"),
    ("Melba Roy Mouton", "(650) 555-0108"),
    ("Evelyn Boyd Granville", "(415) 555-0109"),
    ("Marie Van Brittan Brown", "(628) 555-0110"),
    ("Gladys West", "(510) 555-0111"),
    ("Shirley Ann Jackson", "(650) 555-0112"),
    ("Roy Clay Sr", "(415) 555-0113"),
    ("Mark Dean", "(628) 555-0114"),
]

NOTES = [None, None, None, "window seat if possible", "birthday", "anniversary",
         "high chair needed", "celebrating a promotion"]

DAYS_BACK = 3   # so navigating to earlier dates shows completed history
DAYS_AHEAD = 8


def run(seed: int = 42) -> None:
    rng = random.Random(seed)
    now = datetime.now()
    today = now.date()

    with Session(engine) as session:
        session.exec(text("TRUNCATE reservations, calls RESTART IDENTITY CASCADE"))
        session.commit()

        made = 0
        for offset in range(-DAYS_BACK, DAYS_AHEAD):
            d = today + timedelta(days=offset)
            windows = CONFIG.windows_for(d)
            if not windows:
                continue

            open_dt = datetime.combine(d, windows[0][0])
            last_dt = datetime.combine(d, CONFIG.last_seating(d))
            slots = []
            t = open_dt
            while t <= last_dt:
                slots.append(t)
                t += timedelta(minutes=30)

            k = min(rng.randint(6, 9), len(slots))
            guests = rng.sample(GUESTS, k)
            day_bookings: list[Booking] = []

            for when, (name, phone) in zip(sorted(rng.sample(slots, k)), guests):
                party = rng.choice([2, 2, 2, 3, 4, 4, 5, 6])
                table_id = assign_table(when, party, day_bookings, CONFIG)
                if table_id is None:
                    continue

                ends = when + CONFIG.turn_time
                is_past = ends <= now
                if is_past:
                    status = rng.choices(
                        [STATUS_COMPLETED, STATUS_NO_SHOW, STATUS_BOOKED],
                        weights=[7, 1, 2],
                    )[0]
                else:
                    status = STATUS_CANCELLED if rng.random() < 0.08 else STATUS_BOOKED

                session.add(Reservation(
                    confirmation_code=_generate_code(session),
                    guest_name=name,
                    phone=phone,
                    party_size=party,
                    start_at=when,
                    end_at=ends,
                    table_id=table_id,
                    status=status,
                    source="voice" if rng.random() < 0.4 else "manual",
                    notes=rng.choice(NOTES),
                ))
                day_bookings.append(Booking(table_id=table_id, start=when, end=ends))
                made += 1

            session.commit()
            print(f"  {d:%a %d %b}: {len(day_bookings)} reservations")

        print(f"\nseeded {made} reservations from {DAYS_BACK} days ago "
              f"through {DAYS_AHEAD - 1} days ahead")


if __name__ == "__main__":
    run()
