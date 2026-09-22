"""REST API for reservations. Consumed by the demo web app and exercised by tests.

The voice agent does NOT go through HTTP — its tool handlers call the functions in
`service.py` directly. Same logic, one less hop.
"""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.db import get_session
from app.models import STATUS_BOOKED
from app.reservations import service
from app.reservations.availability import CannotResolveDateTime, resolve_when
from app.reservations.schemas import (
    AlternativeSlot,
    AvailabilityOut,
    CreateReservationIn,
    DayAvailabilityOut,
    DaySlotOut,
    HoursWindowOut,
    PatchReservationIn,
    ReservationOut,
    RestaurantConfigOut,
    TableOut,
)
from app.restaurant_config import CONFIG

router = APIRouter(prefix="/api", tags=["reservations"])

_WEEKDAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _parse_when(raw: str) -> datetime:
    try:
        return resolve_when(raw)
    except CannotResolveDateTime as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e


def _availability_payload(res) -> AvailabilityOut:
    return AvailabilityOut(
        available=res.available,
        requested=res.requested,
        party_size=res.party_size,
        table_id=res.table_id,
        reason=res.reason,
        alternatives=[AlternativeSlot(when=a) for a in res.alternatives],
    )


@router.get("/config", response_model=RestaurantConfigOut)
def get_config() -> RestaurantConfigOut:
    return RestaurantConfigOut(
        name=CONFIG.name,
        timezone=CONFIG.timezone,
        phone=CONFIG.phone,
        address=CONFIG.address,
        turn_time_minutes=int(CONFIG.turn_time.total_seconds() // 60),
        slot_granularity_minutes=int(CONFIG.slot_granularity.total_seconds() // 60),
        max_party_size=CONFIG.max_party_size,
        booking_horizon_days=CONFIG.booking_horizon_days,
        hours={
            _WEEKDAY_NAMES[wd]: [
                HoursWindowOut(open=o.strftime("%H:%M"), close=c.strftime("%H:%M"))
                for o, c in windows
            ]
            for wd, windows in CONFIG.hours.items()
        },
        tables=[TableOut(id=t.id, capacity=t.capacity, section=t.section) for t in CONFIG.tables],
    )


@router.get("/availability", response_model=AvailabilityOut)
def get_availability(
    when: str = Query(..., description="ISO datetime or free text"),
    party_size: int = Query(..., ge=1, le=50),
    session: Session = Depends(get_session),
) -> AvailabilityOut:
    res = service.check_slot(session, _parse_when(when), party_size)
    return _availability_payload(res)


@router.get("/availability/day", response_model=DayAvailabilityOut)
def get_day_availability(
    date_: date = Query(..., alias="date"),
    party_size: int = Query(..., ge=1, le=50),
    session: Session = Depends(get_session),
) -> DayAvailabilityOut:
    """Per-slot openings for one day — powers the reservation form's openings strip."""
    day = service.day_availability(session, date_, party_size)
    return DayAvailabilityOut(
        date=day.date,
        party_size=day.party_size,
        slot_minutes=int(CONFIG.slot_granularity.total_seconds() // 60),
        windows=[
            HoursWindowOut(open=o.strftime("%H:%M"), close=c.strftime("%H:%M"))
            for o, c in day.windows
        ],
        reason=day.reason,
        next_open_date=day.next_open_date,
        slots=[
            DaySlotOut(time=s.time, free_tables=s.free_tables, bookable=s.bookable)
            for s in day.slots
        ],
    )


@router.get("/reservations", response_model=list[ReservationOut])
def list_reservations(
    day: date | None = Query(None),
    upcoming: bool = Query(False),
    session: Session = Depends(get_session),
) -> list[ReservationOut]:
    rows = service.list_reservations(session, day=day, upcoming_only=upcoming)
    return [ReservationOut.of(r) for r in rows]


@router.post("/reservations", response_model=ReservationOut, status_code=status.HTTP_201_CREATED)
def create_reservation(
    body: CreateReservationIn,
    session: Session = Depends(get_session),
) -> ReservationOut:
    try:
        r = service.create_reservation(
            session,
            guest_name=body.guest_name,
            phone=body.phone,
            party_size=body.party_size,
            when=_parse_when(body.when),
            source=body.source,
            notes=body.notes,
            idempotency_key=body.idempotency_key,
        )
    except service.NoAvailability as e:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=_availability_payload(e.result).model_dump(mode="json"),
        ) from e
    return ReservationOut.of(r)


@router.get("/reservations/{code}", response_model=ReservationOut)
def get_reservation(code: str, session: Session = Depends(get_session)) -> ReservationOut:
    try:
        return ReservationOut.of(service.get_by_code(session, code))
    except service.ReservationNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "reservation not found") from e


@router.patch("/reservations/{code}", response_model=ReservationOut)
def patch_reservation(
    code: str, body: PatchReservationIn, session: Session = Depends(get_session)
) -> ReservationOut:
    try:
        r = service.update_reservation(session, code, status=body.status, notes=body.notes)
    except service.ReservationNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "reservation not found") from e
    except service.InvalidStatus as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "bad status") from e
    return ReservationOut.of(r)


@router.delete("/reservations/{code}", response_model=ReservationOut)
def cancel_reservation(code: str, session: Session = Depends(get_session)) -> ReservationOut:
    try:
        return ReservationOut.of(service.cancel_reservation(session, code))
    except service.ReservationNotFound as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "reservation not found") from e


@router.get("/day", response_model=list[ReservationOut])
def day_view(
    date_: date = Query(..., alias="date"),
    session: Session = Depends(get_session),
) -> list[ReservationOut]:
    rows = service.list_reservations(session, day=date_)
    return [ReservationOut.of(r) for r in rows if r.status in {STATUS_BOOKED}]
