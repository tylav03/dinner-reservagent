"""Single-restaurant configuration for the demo.

Everything the availability engine needs to reason about the venue lives here:
opening hours, the physical table inventory, how long a table is held per
booking ("turn time"), and booking limits. Keeping it in one typed module means
the voice agent, the REST API, and the tests all share exactly one definition of
"the restaurant".

For a real multi-tenant system this would be rows in a `restaurants` table; the
demo deliberately hard-codes one venue to keep the conflict logic easy to follow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

# Weekday index (Mon=0 .. Sun=6) -> list of (open, close) windows for that day.
# A day with an empty list is a closed day.
Weekday = int
HoursWindow = tuple[time, time]


@dataclass(frozen=True)
class TableSpec:
    """One physical table the host can seat a party at."""

    id: str
    capacity: int
    section: str = "main"


@dataclass(frozen=True)
class RestaurantConfig:
    name: str
    timezone: str
    phone: str
    address: str
    turn_time: timedelta                       # how long one booking occupies a table
    slot_granularity: timedelta                # bookings start on these boundaries
    max_party_size: int                        # larger parties -> human callback
    booking_horizon_days: int                  # how far ahead guests may book
    hours: dict[Weekday, list[HoursWindow]]
    tables: list[TableSpec] = field(default_factory=list)

    # --- derived helpers -------------------------------------------------

    def windows_for(self, d: date) -> list[HoursWindow]:
        """Opening windows that apply to a specific calendar date."""
        return self.hours.get(d.weekday(), [])

    def is_within_hours(self, start: datetime) -> bool:
        """True if a booking that *starts* at `start` also *ends* (start +
        turn_time) inside the same opening window. A 7:00pm booking with a 90m
        turn time is invalid if the kitchen closes at 8:00pm."""
        end = (start + self.turn_time).time()
        s = start.time()
        for open_t, close_t in self.windows_for(start.date()):
            if s >= open_t and end <= close_t:
                return True
        return False

    def last_seating(self, d: date) -> time | None:
        """Latest start time that still fits a full turn before close."""
        windows = self.windows_for(d)
        if not windows:
            return None
        close_t = max(close for _, close in windows)
        latest = (datetime.combine(d, close_t) - self.turn_time).time()
        return latest

    def largest_table_capacity(self) -> int:
        return max((t.capacity for t in self.tables), default=0)


def _t(hhmm: str) -> time:
    hh, mm = hhmm.split(":")
    return time(int(hh), int(mm))


# Mon=0 .. Sun=6
_DINNER = [( _t("17:00"), _t("22:00") )]
_DINNER_LATE = [( _t("17:00"), _t("23:00") )]
_WEEKEND = [( _t("16:00"), _t("23:00") )]

CONFIG = RestaurantConfig(
    name="The Copper Fork",
    timezone="America/New_York",
    phone="(212) 555-0142",
    address="128 Mill Street, New York, NY",
    turn_time=timedelta(minutes=90),
    slot_granularity=timedelta(minutes=15),
    max_party_size=8,
    booking_horizon_days=60,
    hours={
        0: [],             # Monday — closed
        1: _DINNER,        # Tuesday
        2: _DINNER,        # Wednesday
        3: _DINNER,        # Thursday
        4: _DINNER_LATE,   # Friday
        5: _WEEKEND,       # Saturday
        6: [(_t("16:00"), _t("21:00"))],  # Sunday
    },
    tables=[
        TableSpec("T1", 2), TableSpec("T2", 2), TableSpec("T3", 2), TableSpec("T4", 2),
        TableSpec("T5", 4), TableSpec("T6", 4), TableSpec("T7", 4), TableSpec("T8", 4),
        TableSpec("T9", 4), TableSpec("T10", 4),
        TableSpec("T11", 6), TableSpec("T12", 6),
        TableSpec("T13", 6, section="patio"), TableSpec("T14", 6, section="patio"),
    ],
)


def now_local(config: RestaurantConfig = CONFIG) -> datetime:
    """Current wall-clock time in the restaurant's timezone, as a *naive*
    datetime — the whole app models booking times as naive local time.

    Use this instead of `datetime.now()` for any past/future decision. The
    process may run in UTC (e.g. a Docker container), so `datetime.now()` there
    is not the restaurant's clock.
    """
    return datetime.now(ZoneInfo(config.timezone)).replace(tzinfo=None)
