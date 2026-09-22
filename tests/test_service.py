"""Transactional layer: create / lookup / cancel / idempotency. Needs Postgres."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.models import STATUS_BOOKED, STATUS_CANCELLED, STATUS_SEATED
from app.reservations import service
from app.restaurant_config import CONFIG


def _friday_7pm() -> datetime:
    d = datetime.now().date()
    while d.weekday() != 4:
        d += timedelta(days=1)
    d += timedelta(days=7)  # a Friday comfortably in the future
    return datetime(d.year, d.month, d.day, 19, 0)


def test_create_and_lookup(session):
    r = service.create_reservation(
        session, guest_name="Ada Lovelace", phone="+15550100",
        party_size=2, when=_friday_7pm(),
    )
    assert r.confirmation_code and r.table_id == "T1"
    assert r.status == STATUS_BOOKED
    assert r.end_at - r.start_at == CONFIG.turn_time

    again = service.get_by_code(session, r.confirmation_code.lower())  # case-insensitive
    assert again.id == r.id


def test_second_party_gets_a_different_table(session):
    when = _friday_7pm()
    a = service.create_reservation(session, guest_name="A", phone="1", party_size=2, when=when)
    b = service.create_reservation(session, guest_name="B", phone="2", party_size=2, when=when)
    assert a.table_id != b.table_id


def test_no_availability_raises_with_alternatives(session):
    when = _friday_7pm()
    for i in range(len(CONFIG.tables)):
        service.create_reservation(
            session, guest_name=f"G{i}", phone=str(i), party_size=2, when=when
        )
    with pytest.raises(service.NoAvailability) as ei:
        service.create_reservation(
            session, guest_name="late", phone="9", party_size=2, when=when
        )
    assert ei.value.result.reason == "full"
    assert ei.value.result.alternatives


def test_idempotency_key_returns_same_row(session):
    when = _friday_7pm()
    key = "call-sid-abc123"
    r1 = service.create_reservation(
        session, guest_name="Grace", phone="+15550111", party_size=4,
        when=when, idempotency_key=key,
    )
    r2 = service.create_reservation(
        session, guest_name="Grace (retry)", phone="+15550111", party_size=4,
        when=when, idempotency_key=key,
    )
    assert r1.id == r2.id
    assert r2.guest_name == "Grace"  # original wins, retry does not mutate


def test_cancel_frees_the_table(session):
    when = _friday_7pm()
    two_tops = [t.id for t in CONFIG.tables if t.capacity == 2]
    made = [
        service.create_reservation(session, guest_name=f"P{i}", phone=str(i),
                                   party_size=2, when=when)
        for i in range(len(two_tops))
    ]
    # a 2-top party now spills onto a 4-top
    spill = service.create_reservation(session, guest_name="spill", phone="x",
                                       party_size=2, when=when)
    assert spill.table_id not in two_tops

    service.cancel_reservation(session, made[0].confirmation_code)
    assert service.get_by_code(session, made[0].confirmation_code).status == STATUS_CANCELLED

    # freed 2-top is reused
    reuse = service.create_reservation(session, guest_name="reuse", phone="y",
                                       party_size=2, when=when)
    assert reuse.table_id == made[0].table_id


def test_update_reservation_changes_status_and_notes(session):
    r = service.create_reservation(session, guest_name="Grace Hopper", phone="1",
                                   party_size=2, when=_friday_7pm())
    # Capture before mutating — `session` uses SQLAlchemy's identity map, so
    # `r` and the object `update_reservation` returns are the *same* Python
    # object for this PK; comparing r.updated_at after the call would just be
    # comparing the mutated value to itself.
    before = r.updated_at
    updated = service.update_reservation(session, r.confirmation_code,
                                         status=STATUS_SEATED, notes="by the window")
    assert updated.status == STATUS_SEATED
    assert updated.notes == "by the window"
    assert updated.updated_at > before


def test_update_reservation_rejects_bad_status(session):
    r = service.create_reservation(session, guest_name="Alan Turing", phone="2",
                                   party_size=2, when=_friday_7pm())
    with pytest.raises(service.InvalidStatus):
        service.update_reservation(session, r.confirmation_code, status="enroute")


def test_update_reservation_unknown_code_raises(session):
    with pytest.raises(service.ReservationNotFound):
        service.update_reservation(session, "NOPE99", status=STATUS_SEATED)


def test_update_reservation_noop_does_not_touch_updated_at(session):
    # Same pattern as cancel_reservation: a PATCH that changes nothing is a
    # no-op write, not just a no-op result. Capture the timestamp before
    # mutating — `r` and update_reservation's return share the same identity
    # (one SQLAlchemy session), so comparing against r.updated_at afterward
    # would just compare the value to itself.
    r = service.create_reservation(session, guest_name="Katherine Johnson", phone="3",
                                   party_size=2, when=_friday_7pm())
    before = r.updated_at

    unchanged = service.update_reservation(session, r.confirmation_code,
                                           status=r.status, notes=r.notes)
    assert unchanged.updated_at == before

    still_unchanged = service.update_reservation(session, r.confirmation_code)
    assert still_unchanged.updated_at == before


def test_past_time_rejected(session):
    past = datetime.now() - timedelta(days=1)
    with pytest.raises(service.NoAvailability) as ei:
        service.create_reservation(session, guest_name="x", phone="1",
                                   party_size=2, when=past)
    assert ei.value.result.reason == "past"


def test_day_availability_reports_openings(session):
    friday = _friday_7pm().date()
    day = service.day_availability(session, friday, 2)
    assert day.reason is None
    assert day.slots[0].time == "17:00"
    assert day.slots[0].free_tables == 14
    assert all(s.bookable for s in day.slots)  # nothing booked yet


def test_day_availability_full_night_points_to_next_open_date(session):
    friday = _friday_7pm().date()
    # Every table that could seat a party of 6 — T11-T14 (6- and 8-tops), not
    # just capacity == 6, or an 8-top would sit empty and the night wouldn't
    # actually be full.
    tables_for_six = [t.id for t in CONFIG.tables if t.capacity >= 6]
    # Fill every one of them for the whole service with back-to-back 90-min turns.
    for tid in tables_for_six:
        for start_h, start_m in [(17, 0), (18, 30), (20, 0), (21, 30)]:
            service.create_reservation(
                session, guest_name=f"{tid}-{start_h}", phone=tid,
                party_size=6, when=datetime.combine(friday, datetime.min.time())
                .replace(hour=start_h, minute=start_m),
            )
    day = service.day_availability(session, friday, 6)
    assert day.reason == "full"
    assert day.next_open_date is not None and day.next_open_date > friday
