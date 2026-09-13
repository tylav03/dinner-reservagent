"""Request / response shapes for the reservation API.

Kept separate from the ORM models so the wire format can evolve independently of
the table layout.
"""

from __future__ import annotations

from datetime import date, datetime

from typing import Literal

from pydantic import BaseModel, Field

from app.models import Reservation


class CreateReservationIn(BaseModel):
    guest_name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=3, max_length=40)
    party_size: int = Field(ge=1, le=50)
    # Either an ISO datetime ("2026-09-05T19:00") or free text ("next Friday 7pm").
    when: str
    notes: str | None = Field(default=None, max_length=500)
    idempotency_key: str | None = Field(default=None, max_length=120)
    # Who made the booking. Defaults to "manual" (a person using a dashboard).
    # The voice agent calls the service layer directly with source="voice";
    # external integrations can pass "api".
    source: Literal["manual", "api", "voice"] = "manual"


class PatchReservationIn(BaseModel):
    status: str | None = None
    notes: str | None = Field(default=None, max_length=500)


class ReservationOut(BaseModel):
    id: str
    confirmation_code: str
    guest_name: str
    phone: str
    party_size: int
    start_at: datetime
    end_at: datetime
    table_id: str | None
    status: str
    source: str
    notes: str | None

    @classmethod
    def of(cls, r: Reservation) -> "ReservationOut":
        return cls(**r.model_dump(include=set(cls.model_fields)))


class AlternativeSlot(BaseModel):
    when: datetime


class AvailabilityOut(BaseModel):
    available: bool
    requested: datetime
    party_size: int
    table_id: str | None = None
    reason: str | None = None
    alternatives: list[AlternativeSlot] = []


class HoursWindowOut(BaseModel):
    open: str
    close: str


class DaySlotOut(BaseModel):
    time: str            # "HH:MM"
    free_tables: int
    bookable: bool


class DayAvailabilityOut(BaseModel):
    date: date
    party_size: int
    slot_minutes: int
    windows: list[HoursWindowOut]           # [] when closed
    reason: str | None = None              # None when the day has openings
    next_open_date: date | None = None
    slots: list[DaySlotOut]


class TableOut(BaseModel):
    id: str
    capacity: int
    section: str


class RestaurantConfigOut(BaseModel):
    name: str
    timezone: str
    phone: str
    address: str
    turn_time_minutes: int
    slot_granularity_minutes: int
    max_party_size: int
    booking_horizon_days: int
    hours: dict[str, list[HoursWindowOut]]   # weekday name -> windows
    tables: list[TableOut]
