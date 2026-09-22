"""Transactional reservation operations.

This is the I/O shell around the pure engine in `availability.py`. Everything that
needs a database connection, a lock, or a transaction lives here.

The double-booking race
-----------------------
Creating a booking is a read-modify-write: *check* what's on the books, *decide*
a table, *insert*. If two calls do that concurrently for the same evening they can
both pass the check and both insert.

Guard, in order of strength:

1. `pg_advisory_xact_lock(<hash of the service date>)` at the top of
   `create_reservation`. Postgres serializes every writer for that calendar day;
   writers for other days still run in parallel. The lock releases automatically
   when the transaction ends. This makes check->insert atomic without raising the
   whole transaction to SERIALIZABLE isolation.

2. A partial unique index `(table_id, start_at) WHERE status = 'booked'`
   (see `models.py`) as a belt-and-braces backstop: even if the lock were
   bypassed, the second identical insert fails with IntegrityError.

`tests/test_concurrency.py` fires two real concurrent creates at one slot and
asserts exactly one wins.
"""

from __future__ import annotations

import secrets
import zlib
from datetime import date, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.models import (
    SOURCE_MANUAL,
    STATUS_BOOKED,
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_NO_SHOW,
    STATUS_SEATED,
    Reservation,
)
from app.reservations.availability import (
    REASON_CLOSED,
    REASON_FULL,
    REASON_PARTY_TOO_LARGE,
    REASON_PAST,
    AvailabilityResult,
    Booking,
    check_availability,
    free_tables_at,
    snap_to_slot,
)
from app.restaurant_config import CONFIG, RestaurantConfig, now_local

# Confirmation codes: 6 chars, no visually ambiguous glyphs (no I/O/0/1).
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class NoAvailability(Exception):
    """Raised by create_reservation when the requested slot can't be booked.
    Carries the engine's result so the caller can offer alternatives."""

    def __init__(self, result: AvailabilityResult):
        self.result = result
        super().__init__(result.reason or "no availability")


class ReservationNotFound(Exception):
    pass


class InvalidStatus(Exception):
    """Raised by update_reservation for a status outside the allowed set."""


# ---------------------------------------------------------------------------
# reads
# ---------------------------------------------------------------------------

def _bookings_overlapping(session: Session, when: datetime,
                          config: RestaurantConfig, *, lock: bool) -> list[Booking]:
    """Booked reservations whose window overlaps [when, when + turn_time).

    With lock=True the rows are taken FOR UPDATE (used inside create_reservation).
    """
    window_end = when + config.turn_time
    stmt = select(Reservation).where(
        Reservation.status == STATUS_BOOKED,
        Reservation.start_at < window_end,
        Reservation.end_at > when,
    )
    if lock:
        stmt = stmt.with_for_update()
    rows = session.exec(stmt).all()
    return [
        Booking(table_id=r.table_id, start=r.start_at, end=r.end_at, reservation_id=r.id)
        for r in rows
        if r.table_id is not None
    ]


def check_slot(session: Session, when: datetime, party_size: int, *,
               now: datetime | None = None,
               config: RestaurantConfig = CONFIG) -> AvailabilityResult:
    """Read-only availability check. Used by GET /api/availability and by the
    voice agent's `check_availability` tool. No locking, no writes."""
    when = snap_to_slot(when, config.slot_granularity)
    existing = _bookings_overlapping(session, when, config, lock=False)
    # nearest_alternatives may probe other times on the same day; give it that
    # day's bookings, not just the requested window's.
    day_bookings = bookings_on_day(session, when.date(), config=config)
    merged = {(b.table_id, b.start): b for b in (*existing, *day_bookings)}
    return check_availability(when, party_size, list(merged.values()),
                              now=now, config=config)


def bookings_on_day(session: Session, day: date, *,
                    config: RestaurantConfig = CONFIG) -> list[Booking]:
    start = datetime.combine(day, datetime.min.time())
    stmt = select(Reservation).where(
        Reservation.status == STATUS_BOOKED,
        Reservation.start_at >= start,
        Reservation.start_at < start + timedelta(days=1),
    )
    rows = session.exec(stmt).all()
    return [
        Booking(table_id=r.table_id, start=r.start_at, end=r.end_at, reservation_id=r.id)
        for r in rows if r.table_id is not None
    ]


class DaySlot:
    """One bookable slot on a day, for the openings strip."""

    __slots__ = ("time", "free_tables", "bookable")

    def __init__(self, time: str, free_tables: int, bookable: bool):
        self.time = time
        self.free_tables = free_tables
        self.bookable = bookable


class DayAvailability:
    __slots__ = ("date", "party_size", "windows", "slots", "reason", "next_open_date")

    def __init__(self, *, date, party_size, windows, slots, reason, next_open_date):
        self.date = date
        self.party_size = party_size
        self.windows = windows                 # list[(open_time, close_time)]
        self.slots = slots                     # list[DaySlot]
        self.reason = reason                   # None | "closed"|"party_too_large"|"past"|"full"
        self.next_open_date = next_open_date    # date | None


def _day_slots(session: Session, d: date, party_size: int, now: datetime,
               config: RestaurantConfig) -> tuple[list[DaySlot], bool, bool]:
    """Per-slot free-table counts for one day. Returns (slots, any_bookable,
    any_future)."""
    windows = config.windows_for(d)
    if not windows:
        return [], False, False

    day_bookings = bookings_on_day(session, d, config=config)
    step = config.slot_granularity
    open_dt = datetime.combine(d, min(o for o, _ in windows))
    last_dt = datetime.combine(d, config.last_seating(d))

    slots: list[DaySlot] = []
    any_bookable = any_future = False
    t = open_dt
    while t <= last_dt:
        free = free_tables_at(t, party_size, day_bookings, config)
        is_future = t >= now
        bookable = free > 0 and is_future
        any_bookable |= bookable
        any_future |= is_future
        slots.append(DaySlot(t.strftime("%H:%M"), free, bookable))
        t += step
    return slots, any_bookable, any_future


def _find_next_open_date(session: Session, start: date, party_size: int,
                         now: datetime, config: RestaurantConfig,
                         horizon_days: int = 14) -> date | None:
    """The nearest date after `start` (within `horizon_days`) that has at least
    one bookable slot for this party. Only called when `start` itself is a bust."""
    if party_size > config.max_party_size:
        return None
    for i in range(1, horizon_days + 1):
        d = start + timedelta(days=i)
        _, any_bookable, _ = _day_slots(session, d, party_size, now, config)
        if any_bookable:
            return d
    return None


def day_availability(session: Session, d: date, party_size: int, *,
                     now: datetime | None = None,
                     config: RestaurantConfig = CONFIG) -> DayAvailability:
    """Everything the openings strip needs for one day: the slot grid, and — if
    the day is unusable — why, plus the next date that would work."""
    now = now or now_local(config)
    windows = config.windows_for(d)

    if party_size > config.max_party_size:
        reason = REASON_PARTY_TOO_LARGE
        slots: list[DaySlot] = []
    elif not windows:
        reason = REASON_CLOSED
        slots = []
    else:
        slots, any_bookable, any_future = _day_slots(session, d, party_size, now, config)
        if any_bookable:
            reason = None
        else:
            reason = REASON_PAST if not any_future else REASON_FULL

    next_open = None
    if reason in (REASON_CLOSED, REASON_FULL, REASON_PAST):
        next_open = _find_next_open_date(session, d, party_size, now, config)

    return DayAvailability(
        date=d, party_size=party_size, windows=windows,
        slots=slots, reason=reason, next_open_date=next_open,
    )


def get_by_code(session: Session, confirmation_code: str) -> Reservation:
    row = session.exec(
        select(Reservation).where(Reservation.confirmation_code == confirmation_code.upper())
    ).first()
    if row is None:
        raise ReservationNotFound(confirmation_code)
    return row


def find_by_phone(session: Session, phone: str) -> list[Reservation]:
    return list(session.exec(
        select(Reservation)
        .where(Reservation.phone == phone, Reservation.status == STATUS_BOOKED)
        .order_by(Reservation.start_at)
    ).all())


def list_reservations(session: Session, *, day: date | None = None,
                      upcoming_only: bool = False) -> list[Reservation]:
    stmt = select(Reservation)
    if day is not None:
        start = datetime.combine(day, datetime.min.time())
        stmt = stmt.where(Reservation.start_at >= start,
                          Reservation.start_at < start + timedelta(days=1))
    if upcoming_only:
        stmt = stmt.where(Reservation.start_at >= now_local())
    return list(session.exec(stmt.order_by(Reservation.start_at)).all())


# ---------------------------------------------------------------------------
# writes
# ---------------------------------------------------------------------------

def _day_lock_key(d: date) -> int:
    """Stable 63-bit-safe int key for pg_advisory_xact_lock, one per calendar day."""
    return zlib.crc32(d.isoformat().encode()) & 0x7FFFFFFF


def _generate_code(session: Session) -> str:
    for _ in range(10):
        code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))
        exists = session.exec(
            select(Reservation.id).where(Reservation.confirmation_code == code)
        ).first()
        if not exists:
            return code
    raise RuntimeError("could not generate a unique confirmation code")


def create_reservation(
    session: Session,
    *,
    guest_name: str,
    phone: str,
    party_size: int,
    when: datetime,
    source: str = SOURCE_MANUAL,
    notes: str | None = None,
    idempotency_key: str | None = None,
    now: datetime | None = None,
    config: RestaurantConfig = CONFIG,
) -> Reservation:
    """Book a table, atomically. Raises NoAvailability if the slot can't be had.

    If `idempotency_key` was used before, the original reservation is returned
    unchanged (safe to retry).
    """
    when = snap_to_slot(when, config.slot_granularity)

    if idempotency_key:
        prior = session.exec(
            select(Reservation).where(Reservation.idempotency_key == idempotency_key)
        ).first()
        if prior is not None:
            return prior

    # Serialize all writers for this service day.
    session.exec(text("SELECT pg_advisory_xact_lock(:k)").bindparams(k=_day_lock_key(when.date())))

    existing = _bookings_overlapping(session, when, config, lock=True)
    day_bookings = bookings_on_day(session, when.date(), config=config)
    merged = {(b.table_id, b.start): b for b in (*existing, *day_bookings)}

    result = check_availability(when, party_size, list(merged.values()),
                                now=now, config=config)
    if not result.available:
        raise NoAvailability(result)

    reservation = Reservation(
        confirmation_code=_generate_code(session),
        guest_name=guest_name.strip(),
        phone=phone.strip(),
        party_size=party_size,
        start_at=when,
        end_at=when + config.turn_time,
        table_id=result.table_id,
        status=STATUS_BOOKED,
        source=source,
        notes=notes,
        idempotency_key=idempotency_key,
    )
    session.add(reservation)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        # Lost a race on the unique index, or a duplicate idempotency key landed
        # concurrently. Re-resolve.
        if idempotency_key:
            prior = session.exec(
                select(Reservation).where(Reservation.idempotency_key == idempotency_key)
            ).first()
            if prior is not None:
                return prior
        raise NoAvailability(check_slot(session, when, party_size, now=now, config=config))
    session.refresh(reservation)
    return reservation


def cancel_reservation(session: Session, confirmation_code: str) -> Reservation:
    row = get_by_code(session, confirmation_code)
    if row.status != STATUS_CANCELLED:
        row.status = STATUS_CANCELLED
        row.updated_at = now_local()
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


_VALID_STATUSES = {STATUS_BOOKED, STATUS_SEATED, STATUS_COMPLETED, STATUS_CANCELLED, STATUS_NO_SHOW}


def update_reservation(
    session: Session, confirmation_code: str, *,
    status: str | None = None, notes: str | None = None,
) -> Reservation:
    """Patch a reservation's status and/or notes. Raises ReservationNotFound for
    a bad code, InvalidStatus for a status outside the allowed set. Like
    cancel_reservation, only writes (and bumps updated_at) if something actually
    changed — a no-op PATCH is a no-op write.
    """
    row = get_by_code(session, confirmation_code)

    if status is not None and status not in _VALID_STATUSES:
        raise InvalidStatus(status)

    changed = False
    if status is not None and status != row.status:
        row.status = status
        changed = True
    if notes is not None and notes != row.notes:
        row.notes = notes
        changed = True

    if changed:
        row.updated_at = now_local()
        session.add(row)
        session.commit()
        session.refresh(row)
    return row
