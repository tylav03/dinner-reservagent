"""Transactional layer: create / lookup / cancel / idempotency. Needs Postgres."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.models import STATUS_BOOKED, STATUS_CANCELLED
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


def test_past_time_rejected(session):
    past = datetime.now() - timedelta(days=1)
    with pytest.raises(service.NoAvailability) as ei:
        service.create_reservation(session, guest_name="x", phone="1",
                                   party_size=2, when=past)
    assert ei.value.result.reason == "past"
