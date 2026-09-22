"""Tools the agent (text-mode today, the phone agent from Phase 5) can call.

These call `service.py` directly — never the REST API — same principle as
`router.py`'s module docstring: the voice path and the HTTP path both sit on
top of one shared service layer, so a booking made by phone and one made by a
host at the dashboard are checked against, and can conflict with, each other
identically.

Every handler takes a DB session plus keyword arguments matching its JSON
schema below, and returns a plain JSON-serializable dict — never an ORM
object, never a raised exception. The model only ever sees clean dicts: a
domain failure (no availability, bad code, ...) comes back as
`{"ok": False, "reason": ...}`, not a stack trace. That's deliberate — a phone
call can't recover from an unhandled exception in a tool call, so nothing here
is allowed to raise past `call_tool`.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlmodel import Session

from app.models import SOURCE_VOICE
from app.reservations import service
from app.reservations.availability import CannotResolveDateTime, resolve_when


def _parse_when(date_str: str, time_str: str) -> datetime:
    """"YYYY-MM-DD" + "HH:MM" -> datetime. Falls back to free-text parsing (via
    resolve_when) if the model sends something looser than the schema asks for
    — models are good but not perfectly obedient about format."""
    try:
        return datetime.fromisoformat(f"{date_str}T{time_str}")
    except ValueError:
        return resolve_when(f"{date_str} {time_str}")


def _slot_dict(when: datetime) -> dict[str, str]:
    return {"date": when.date().isoformat(), "time": when.strftime("%H:%M")}


# ---------------------------------------------------------------------------
# handlers
# ---------------------------------------------------------------------------

def check_availability(
    session: Session, *, date: str, time: str, party_size: int,
) -> dict[str, Any]:
    when = _parse_when(date, time)
    result = service.check_slot(session, when, party_size)
    out: dict[str, Any] = {
        "available": result.available,
        "date": result.requested.date().isoformat(),
        "time": result.requested.strftime("%H:%M"),
        "party_size": result.party_size,
    }
    if result.available:
        out["table_id"] = result.table_id
    else:
        out["reason"] = result.reason
        out["alternatives"] = [_slot_dict(a) for a in result.alternatives]
    return out


def create_reservation(
    session: Session, *, guest_name: str, phone: str, party_size: int,
    date: str, time: str, notes: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    when = _parse_when(date, time)
    try:
        r = service.create_reservation(
            session,
            guest_name=guest_name,
            phone=phone,
            party_size=party_size,
            when=when,
            source=SOURCE_VOICE,
            notes=notes,
            idempotency_key=idempotency_key,
        )
    except service.NoAvailability as e:
        return {
            "booked": False,
            "reason": e.result.reason,
            "alternatives": [_slot_dict(a) for a in e.result.alternatives],
        }
    return {
        "booked": True,
        "confirmation_code": r.confirmation_code,
        "guest_name": r.guest_name,
        "party_size": r.party_size,
        "date": r.start_at.date().isoformat(),
        "time": r.start_at.strftime("%H:%M"),
        "table_id": r.table_id,
    }


def lookup_reservation(
    session: Session, *, confirmation_code: str | None = None,
    phone: str | None = None,
) -> dict[str, Any]:
    if confirmation_code:
        try:
            r = service.get_by_code(session, confirmation_code)
        except service.ReservationNotFound:
            return {"found": False}
        return {"found": True, "reservations": [_reservation_dict(r)]}

    if phone:
        rows = service.find_by_phone(session, phone)
        return {"found": bool(rows), "reservations": [_reservation_dict(r) for r in rows]}

    return {"found": False, "error": "provide a confirmation_code or a phone number"}


def cancel_reservation(session: Session, *, confirmation_code: str) -> dict[str, Any]:
    try:
        r = service.cancel_reservation(session, confirmation_code)
    except service.ReservationNotFound:
        return {"cancelled": False, "reason": "no reservation with that confirmation code"}
    return {"cancelled": True, "confirmation_code": r.confirmation_code}


def _reservation_dict(r) -> dict[str, Any]:
    return {
        "confirmation_code": r.confirmation_code,
        "guest_name": r.guest_name,
        "party_size": r.party_size,
        "date": r.start_at.date().isoformat(),
        "time": r.start_at.strftime("%H:%M"),
        "status": r.status,
    }


# ---------------------------------------------------------------------------
# OpenAI function-calling schemas + dispatch
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": (
                "Check whether a table is free for a given date, time, and party "
                "size before promising anything to the caller. Always call this "
                "before create_reservation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "ISO date, YYYY-MM-DD"},
                    "time": {"type": "string", "description": "24-hour time, HH:MM"},
                    "party_size": {"type": "integer", "minimum": 1},
                },
                "required": ["date", "time", "party_size"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_reservation",
            "description": (
                "Book the table. Only call this after check_availability reported "
                "the slot available AND the guest has confirmed the date, time, "
                "party size, and their name out loud."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "guest_name": {"type": "string"},
                    "phone": {"type": "string", "description": "callback number"},
                    "party_size": {"type": "integer", "minimum": 1},
                    "date": {"type": "string", "description": "ISO date, YYYY-MM-DD"},
                    "time": {"type": "string", "description": "24-hour time, HH:MM"},
                    "notes": {"type": "string", "description": "optional: seating request, occasion, etc."},
                },
                "required": ["guest_name", "phone", "party_size", "date", "time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_reservation",
            "description": "Find an existing reservation by its confirmation code or the caller's phone number.",
            "parameters": {
                "type": "object",
                "properties": {
                    "confirmation_code": {"type": "string"},
                    "phone": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_reservation",
            "description": "Cancel an existing reservation by its confirmation code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "confirmation_code": {"type": "string"},
                },
                "required": ["confirmation_code"],
            },
        },
    },
]

_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "check_availability": check_availability,
    "create_reservation": create_reservation,
    "lookup_reservation": lookup_reservation,
    "cancel_reservation": cancel_reservation,
}


def call_tool(session: Session, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Dispatch one tool call by name. Never raises — a bug or bad input here
    becomes a `{"error": ...}` result the model can react to, not a crashed call."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"error": f"unknown tool: {name}"}
    try:
        return handler(session, **arguments)
    except CannotResolveDateTime as e:
        return {"error": str(e)}
    except TypeError as e:
        return {"error": f"bad arguments for {name}: {e}"}
    except Exception as e:  # noqa: BLE001 - deliberate: nothing may escape to the call
        return {"error": f"internal error in {name}: {e}"}
