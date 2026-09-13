"""Unit tests for the pure availability engine (no database).

These are the tests you walk an interviewer through: they pin down the slot math,
opening-hours enforcement, greedy table assignment, and the alternative-slot
suggestions.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from app.reservations.availability import (
    REASON_BEYOND_HORIZON,
    REASON_CLOSED,
    REASON_FULL,
    REASON_PARTY_TOO_LARGE,
    REASON_PAST,
    Booking,
    CannotResolveDateTime,
    assign_table,
    check_availability,
    free_tables_at,
    intervals_overlap,
    resolve_when,
    snap_to_slot,
)
from app.restaurant_config import CONFIG, TableSpec, now_local

# A fixed "now" so tests are deterministic. It's a Wednesday.
NOW = datetime(2026, 9, 2, 12, 0)


def booking(table_id: str, start: datetime, minutes: int = 90) -> Booking:
    return Booking(table_id=table_id, start=start, end=start + timedelta(minutes=minutes))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

class TestIntervalsOverlap:
    def test_clear_overlap(self):
        a0 = datetime(2026, 9, 2, 19, 0)
        assert intervals_overlap(a0, a0 + timedelta(hours=1),
                                 a0 + timedelta(minutes=30), a0 + timedelta(minutes=90))

    def test_back_to_back_do_not_overlap(self):
        a0 = datetime(2026, 9, 2, 19, 0)
        a1 = a0 + timedelta(minutes=90)
        assert not intervals_overlap(a0, a1, a1, a1 + timedelta(minutes=90))

    def test_disjoint(self):
        a0 = datetime(2026, 9, 2, 19, 0)
        assert not intervals_overlap(a0, a0 + timedelta(minutes=90),
                                     a0 + timedelta(hours=3), a0 + timedelta(hours=4))


class TestSnapToSlot:
    def test_snaps_down_to_quarter_hour(self):
        assert snap_to_slot(datetime(2026, 9, 2, 19, 7), timedelta(minutes=15)) == \
            datetime(2026, 9, 2, 19, 0)

    def test_already_aligned_is_unchanged(self):
        aligned = datetime(2026, 9, 2, 19, 15)
        assert snap_to_slot(aligned, timedelta(minutes=15)) == aligned


class TestResolveWhen:
    def test_iso_string(self):
        assert resolve_when("2026-09-05 19:00", now=NOW) == datetime(2026, 9, 5, 19, 0)

    def test_relative_phrase_resolves_to_future(self):
        # "Friday at 7pm" from a Wednesday -> the coming Friday
        assert resolve_when("Friday at 7pm", now=NOW) == datetime(2026, 9, 4, 19, 0)

    def test_next_and_this_prefixes_are_stripped(self):
        # dateparser returns None for these verbatim; resolve_when strips the prefix
        assert resolve_when("next Friday at 7pm", now=NOW) == datetime(2026, 9, 4, 19, 0)
        assert resolve_when("this Friday at 7pm", now=NOW) == datetime(2026, 9, 4, 19, 0)

    def test_garbage_raises(self):
        with pytest.raises(CannotResolveDateTime):
            resolve_when("sometime-ish maybe", now=NOW)


# ---------------------------------------------------------------------------
# assign_table
# ---------------------------------------------------------------------------

class TestAssignTable:
    def test_prefers_smallest_sufficient_table(self):
        when = datetime(2026, 9, 2, 19, 0)
        # party of 2 should land on a 2-top (T1), not a 4- or 6-top
        assert assign_table(when, 2, existing=[]) == "T1"

    def test_party_of_five_needs_a_six_top(self):
        when = datetime(2026, 9, 2, 19, 0)
        assert assign_table(when, 5, existing=[]) == "T11"

    def test_skips_occupied_tables(self):
        when = datetime(2026, 9, 2, 19, 0)
        existing = [booking("T1", when), booking("T2", when), booking("T3", when)]
        assert assign_table(when, 2, existing) == "T4"

    def test_none_when_all_suitable_tables_taken(self):
        when = datetime(2026, 9, 2, 19, 0)
        two_tops = [t.id for t in CONFIG.tables if t.capacity == 2]
        existing = [booking(tid, when) for tid in two_tops]
        # every 2-top is gone; a party of 2 can still be bumped to a 4-top
        assert assign_table(when, 2, existing) == "T5"

    def test_freed_by_earlier_booking_ending(self):
        earlier = datetime(2026, 9, 2, 17, 0)
        later = datetime(2026, 9, 2, 19, 0)  # 2h later, previous 90m turn has ended
        existing = [booking("T1", earlier)]
        assert assign_table(later, 2, existing) == "T1"


class TestFreeTablesAt:
    def test_counts_all_suitable_tables_when_empty(self):
        when = datetime(2026, 9, 4, 19, 0)
        assert free_tables_at(when, 2, []) == len(CONFIG.tables)  # every table seats 2
        assert free_tables_at(when, 5, []) == sum(
            1 for t in CONFIG.tables if t.capacity >= 5
        )

    def test_subtracts_overlapping_bookings(self):
        when = datetime(2026, 9, 4, 19, 0)
        existing = [booking("T1", when), booking("T2", when)]
        assert free_tables_at(when, 2, existing) == len(CONFIG.tables) - 2

    def test_ignores_non_overlapping_bookings(self):
        when = datetime(2026, 9, 4, 19, 0)
        existing = [booking("T1", datetime(2026, 9, 4, 17, 0))]  # ends 18:30
        assert free_tables_at(when, 2, existing) == len(CONFIG.tables)


# ---------------------------------------------------------------------------
# check_availability
# ---------------------------------------------------------------------------

class TestCheckAvailability:
    def test_happy_path(self):
        when = datetime(2026, 9, 4, 19, 0)  # Friday 7pm, open till 23:00
        res = check_availability(when, 2, existing=[], now=NOW)
        assert res.available and res.table_id == "T1" and res.reason is None

    def test_snaps_requested_time(self):
        res = check_availability(datetime(2026, 9, 4, 19, 7), 2, existing=[], now=NOW)
        assert res.requested == datetime(2026, 9, 4, 19, 0)

    def test_rejects_past(self):
        res = check_availability(datetime(2026, 8, 1, 19, 0), 2, existing=[], now=NOW)
        assert not res.available and res.reason == REASON_PAST

    def test_rejects_beyond_horizon(self):
        res = check_availability(NOW + timedelta(days=90), 2, existing=[], now=NOW)
        assert not res.available and res.reason == REASON_BEYOND_HORIZON

    def test_rejects_party_too_large(self):
        res = check_availability(datetime(2026, 9, 4, 19, 0), 12, existing=[], now=NOW)
        assert not res.available and res.reason == REASON_PARTY_TOO_LARGE

    def test_closed_before_opening(self):
        res = check_availability(datetime(2026, 9, 2, 12, 30), 2, existing=[], now=NOW)
        assert not res.available and res.reason == REASON_CLOSED

    def test_too_late_for_full_turn_is_closed(self):
        # Wed closes 22:00, turn is 90m -> last seating 20:30. 21:00 is invalid.
        res = check_availability(datetime(2026, 9, 2, 21, 0), 2, existing=[], now=NOW)
        assert not res.available and res.reason == REASON_CLOSED

    def test_full_returns_alternatives(self):
        when = datetime(2026, 9, 2, 19, 0)
        # occupy every table for the 19:00 window
        existing = [booking(t.id, when) for t in CONFIG.tables]
        res = check_availability(when, 2, existing, now=NOW)
        assert not res.available and res.reason == REASON_FULL
        assert res.alternatives  # engine offers nearby times
        assert all(alt != when for alt in res.alternatives)

    def test_alternatives_are_actually_bookable(self):
        when = datetime(2026, 9, 2, 19, 0)
        existing = [booking(t.id, when) for t in CONFIG.tables]
        res = check_availability(when, 2, existing, now=NOW)
        for alt in res.alternatives:
            assert assign_table(alt, 2, existing) is not None


class TestConfigDerivedHelpers:
    def test_last_seating_accounts_for_turn_time(self):
        # Friday closes 23:00, 90m turn -> last seating 21:30
        friday = datetime(2026, 9, 4).date()
        assert CONFIG.last_seating(friday).isoformat() == "21:30:00"

    def test_monday_is_closed(self):
        assert CONFIG.windows_for(datetime(2026, 9, 7).date()) == []  # a Monday

    def test_largest_table_capacity(self):
        assert CONFIG.largest_table_capacity() == 6
        bigger = replace(CONFIG, tables=[*CONFIG.tables, TableSpec("T99", 10)])
        assert bigger.largest_table_capacity() == 10


class TestNowLocal:
    """Regression: the process may run in UTC (Docker), but past/future
    decisions must use the *restaurant's* wall clock, or same-day evening
    bookings get wrongly rejected as 'past'."""

    def test_now_local_is_naive_and_in_restaurant_offset(self):
        from datetime import timezone

        local = now_local()
        assert local.tzinfo is None
        utc = datetime.now(timezone.utc).replace(tzinfo=None)
        offset_hours = round((utc - local).total_seconds() / 3600)
        assert offset_hours in (4, 5)  # America/New_York is UTC-4 (EDT) / UTC-5 (EST)
