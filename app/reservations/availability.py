"""Pure availability / conflict logic.

This module is deliberately free of any database or framework code. It answers a
single question:

    "Given the restaurant's rules and the set of reservations already on the
     books, can a party of N be seated starting at time T? If not, why not, and
     what nearby times would work?"

`service.py` is responsible for loading existing bookings out of Postgres and
handing them here as plain `Booking` values. That split keeps this logic trivial
to unit-test (no DB fixture needed) and keeps the transactional/locking concerns
in one place.

Time model: the demo uses **naive local wall-clock time** in the restaurant's
timezone everywhere (DB, engine, API). No `tzinfo` objects. This avoids a whole
category of off-by-one-hour bugs in a single-venue demo. A multi-venue system
would need real timezone-aware datetimes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import dateparser

from app.restaurant_config import CONFIG, RestaurantConfig, now_local

# Reasons an availability check can fail. Kept as string constants so they can be
# returned to the voice agent and asserted on in tests.
REASON_CLOSED = "closed"                 # outside opening hours / closed that day
REASON_PARTY_TOO_LARGE = "party_too_large"
REASON_FULL = "full"                    # open, but every suitable table is taken
REASON_PAST = "past"                    # requested time is in the past
REASON_BEYOND_HORIZON = "beyond_horizon"  # further ahead than we take bookings
REASON_UNPARSEABLE = "unparseable"      # could not turn the text into a datetime


class CannotResolveDateTime(ValueError):
    """Raised when a free-text date/time cannot be parsed."""


@dataclass(frozen=True)
class Booking:
    """An existing held reservation, as far as the engine cares."""

    table_id: str
    start: datetime
    end: datetime
    reservation_id: str | None = None


@dataclass
class AvailabilityResult:
    available: bool
    requested: datetime               # effective start after snapping to a slot
    party_size: int
    table_id: str | None = None       # a concrete free table when available
    alternatives: list[datetime] = field(default_factory=list)
    reason: str | None = None         # None iff available


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def intervals_overlap(a_start: datetime, a_end: datetime,
                      b_start: datetime, b_end: datetime) -> bool:
    """Half-open interval overlap: [a_start, a_end) vs [b_start, b_end).

    Back-to-back bookings (one ends exactly when the next starts) do NOT overlap.
    """
    return a_start < b_end and b_start < a_end


def snap_to_slot(dt: datetime, granularity: timedelta) -> datetime:
    """Round a datetime down to the nearest slot boundary within its day.

    Hosts don't seat at 7:07; they seat at 7:00 or 7:15. We snap down so we never
    silently push a guest later than they asked.
    """
    day_start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    step = int(granularity.total_seconds())
    elapsed = int((dt - day_start).total_seconds())
    snapped = (elapsed // step) * step
    return day_start + timedelta(seconds=snapped)


def resolve_when(text_or_iso: str, *, now: datetime | None = None,
                 config: RestaurantConfig = CONFIG) -> datetime:
    """Turn '2026-09-05 19:00', 'next Friday at 7pm', or 'tomorrow at 8' into a
    naive local datetime. Raises CannotResolveDateTime on failure.

    Note: free-text date parsing is genuinely unreliable. `dateparser` chokes on
    common phrasings like "next Friday at 7pm" (weekday + "next"/"this" + time).
    We strip a leading "next "/"this " as a cheap fix, but the real mitigation is
    in the voice layer: the LLM is told today's date and asked to pass a
    structured ISO datetime, with this function as a fallback only.
    """
    now = now or now_local(config)
    cleaned = text_or_iso.strip()
    low = cleaned.lower()
    for prefix in ("next ", "this ", "coming "):
        if low.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break

    parsed = dateparser.parse(
        cleaned,
        settings={
            "RELATIVE_BASE": now,
            "PREFER_DATES_FROM": "future",
            "RETURN_AS_TIMEZONE_AWARE": False,
        },
    )
    if parsed is None:
        raise CannotResolveDateTime(f"could not parse date/time from {text_or_iso!r}")
    return parsed.replace(second=0, microsecond=0)


# ---------------------------------------------------------------------------
# Table assignment
# ---------------------------------------------------------------------------

def assign_table(when: datetime, party_size: int, existing: list[Booking],
                 config: RestaurantConfig = CONFIG) -> str | None:
    """Greedy smallest-fit table assignment.

    We try the smallest table that can seat the party first, so a 2-top booking
    doesn't burn a 6-top that a later large party will need. Returns a table id,
    or None if every suitable table is already occupied for the requested window.
    """
    end = when + config.turn_time
    taken_at_time = {
        b.table_id for b in existing
        if intervals_overlap(when, end, b.start, b.end)
    }
    # Smallest sufficient capacity first; ties broken by the order the restaurant
    # listed its tables (so T5 is tried before T10, and the host's own
    # preference ordering is respected).
    candidates = sorted(
        (t for i, t in enumerate(config.tables) if t.capacity >= party_size),
        key=lambda t: (t.capacity, config.tables.index(t)),
    )
    for table in candidates:
        if table.id not in taken_at_time:
            return table.id
    return None


def free_tables_at(when: datetime, party_size: int, existing: list[Booking],
                   config: RestaurantConfig = CONFIG) -> int:
    """How many tables that can seat `party_size` are free for the full turn
    starting at `when`. Powers the per-slot counts in the openings strip."""
    end = when + config.turn_time
    taken = {
        b.table_id for b in existing
        if intervals_overlap(when, end, b.start, b.end)
    }
    return sum(
        1 for t in config.tables
        if t.capacity >= party_size and t.id not in taken
    )


def nearest_alternatives(when: datetime, party_size: int, existing: list[Booking],
                         config: RestaurantConfig = CONFIG,
                         limit: int = 3) -> list[datetime]:
    """Up to `limit` open slots on the same day, ordered by closeness to `when`.

    Only scans the requested day. Extending to adjacent days is a natural follow-up.
    """
    windows = config.windows_for(when.date())
    if not windows:
        return []

    step = config.slot_granularity
    day = when.date()
    candidates: list[datetime] = []
    for open_t, _close_t in windows:
        slot = datetime.combine(day, open_t)
        last = config.last_seating(day)
        while last is not None and slot.time() <= last:
            candidates.append(slot)
            slot += step

    candidates = [c for c in candidates if c != when and config.is_within_hours(c)]
    candidates.sort(key=lambda c: abs((c - when).total_seconds()))

    out: list[datetime] = []
    for c in candidates:
        if assign_table(c, party_size, existing, config) is not None:
            out.append(c)
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------------------
# The one function callers use
# ---------------------------------------------------------------------------

def check_availability(when: datetime, party_size: int, existing: list[Booking],
                       *, now: datetime | None = None,
                       config: RestaurantConfig = CONFIG) -> AvailabilityResult:
    """Decide whether `party_size` can be seated at `when`.

    `existing` is every currently-booked reservation (any table, any time). The
    engine filters it down to the relevant window itself.
    """
    now = now or now_local(config)
    when = snap_to_slot(when, config.slot_granularity)
    result = AvailabilityResult(available=False, requested=when, party_size=party_size)

    if when < now:
        result.reason = REASON_PAST
        return result

    if when.date() > (now + timedelta(days=config.booking_horizon_days)).date():
        result.reason = REASON_BEYOND_HORIZON
        return result

    if party_size > config.max_party_size:
        result.reason = REASON_PARTY_TOO_LARGE
        return result

    if not config.is_within_hours(when):
        result.reason = REASON_CLOSED
        result.alternatives = nearest_alternatives(when, party_size, existing, config)
        return result

    table_id = assign_table(when, party_size, existing, config)
    if table_id is None:
        result.reason = REASON_FULL
        result.alternatives = nearest_alternatives(when, party_size, existing, config)
        return result

    result.available = True
    result.table_id = table_id
    return result
