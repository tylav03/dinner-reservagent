"""Tool handlers the agent calls. No LLM involved here — these are plain
Python calls, exercised the same way check_availability/create_reservation
would be called mid-conversation. Needs Postgres.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.models import SOURCE_VOICE
from app.reservations import service
from app.voice import tools


def _friday() -> datetime:
    d = datetime.now().date()
    while d.weekday() != 4:
        d += timedelta(days=1)
    d += timedelta(days=7)  # comfortably in the future
    return datetime(d.year, d.month, d.day, 19, 0)


def _ymd_hm(when: datetime) -> tuple[str, str]:
    return when.date().isoformat(), when.strftime("%H:%M")


class TestCheckAvailability:
    def test_open_slot(self, session):
        d, t = _ymd_hm(_friday())
        out = tools.check_availability(session, date=d, time=t, party_size=2)
        assert out["available"] is True
        assert out["table_id"] == "T1"

    def test_conflict_reports_reason_and_alternatives(self, session):
        when = _friday()
        d, t = _ymd_hm(when)
        for i in range(14):
            service.create_reservation(session, guest_name=f"G{i}", phone=str(i),
                                       party_size=2, when=when)
        out = tools.check_availability(session, date=d, time=t, party_size=2)
        assert out["available"] is False
        assert out["reason"] == "full"
        assert out["alternatives"]  # list of {"date", "time"} dicts
        assert set(out["alternatives"][0]) == {"date", "time"}

    def test_falls_back_to_free_text_when_not_iso(self, session):
        # the schema asks for "YYYY-MM-DD"/"HH:MM", but a model might send
        # something looser — should still resolve rather than error out.
        out = tools.check_availability(session, date="next Friday", time="7pm", party_size=2)
        assert "available" in out


class TestCreateReservation:
    def test_books_with_voice_source(self, session):
        d, t = _ymd_hm(_friday())
        out = tools.create_reservation(
            session, guest_name="Ada Lovelace", phone="(212) 555-0101",
            party_size=2, date=d, time=t, notes="window seat",
        )
        assert out["booked"] is True
        assert out["confirmation_code"]
        row = service.get_by_code(session, out["confirmation_code"])
        assert row.source == SOURCE_VOICE
        assert row.notes == "window seat"

    def test_no_availability_returns_clean_dict_not_exception(self, session):
        when = _friday()
        d, t = _ymd_hm(when)
        for i in range(14):
            service.create_reservation(session, guest_name=f"G{i}", phone=str(i),
                                       party_size=2, when=when)
        out = tools.create_reservation(
            session, guest_name="Late Guest", phone="1", party_size=2, date=d, time=t,
        )
        assert out["booked"] is False
        assert out["reason"] == "full"
        assert out["alternatives"]


class TestLookupReservation:
    def test_found_by_code(self, session):
        d, t = _ymd_hm(_friday())
        made = tools.create_reservation(
            session, guest_name="Grace Hopper", phone="+15550111",
            party_size=2, date=d, time=t,
        )
        out = tools.lookup_reservation(session, confirmation_code=made["confirmation_code"])
        assert out["found"] is True
        assert out["reservations"][0]["guest_name"] == "Grace Hopper"

    def test_not_found_by_code(self, session):
        out = tools.lookup_reservation(session, confirmation_code="NOPE99")
        assert out["found"] is False

    def test_found_by_phone(self, session):
        d, t = _ymd_hm(_friday())
        tools.create_reservation(session, guest_name="Katherine Johnson", phone="+15550122",
                                 party_size=2, date=d, time=t)
        out = tools.lookup_reservation(session, phone="+15550122")
        assert out["found"] is True
        assert len(out["reservations"]) == 1

    def test_neither_arg_is_a_clean_error(self, session):
        out = tools.lookup_reservation(session)
        assert out["found"] is False
        assert "error" in out


class TestCancelReservation:
    def test_cancels(self, session):
        d, t = _ymd_hm(_friday())
        made = tools.create_reservation(session, guest_name="Dorothy Vaughan", phone="1",
                                        party_size=2, date=d, time=t)
        out = tools.cancel_reservation(session, confirmation_code=made["confirmation_code"])
        assert out["cancelled"] is True
        assert service.get_by_code(session, made["confirmation_code"]).status == "cancelled"

    def test_unknown_code_is_a_clean_result_not_exception(self, session):
        out = tools.cancel_reservation(session, confirmation_code="NOPE99")
        assert out["cancelled"] is False


class TestCallToolDispatch:
    def test_dispatches_by_name(self, session):
        d, t = _ymd_hm(_friday())
        out = tools.call_tool(session, "check_availability",
                              {"date": d, "time": t, "party_size": 2})
        assert out["available"] is True

    def test_unknown_tool_name(self, session):
        out = tools.call_tool(session, "delete_the_database", {})
        assert "error" in out

    def test_missing_required_argument_does_not_raise(self, session):
        # party_size is required; nothing should escape as a Python exception —
        # a live call can't recover from a crashed tool handler.
        out = tools.call_tool(session, "check_availability", {"date": "2026-09-04"})
        assert "error" in out
