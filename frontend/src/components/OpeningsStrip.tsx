import { useEffect, useState } from "react";
import type { DayAvailability, DaySlot } from "../api";
import { formatClock, formatDate } from "../lib/time";

/**
 * Availability-first slot picker for the reservation form.
 *
 * Shows every 15-minute slot for the chosen day as a heatmap: green where a
 * table for this party is free (darker = more tables), grey where full, faded
 * where the slot has already passed. Click a green slot to set the time. When
 * the whole day is a bust it explains why and links to the next open date.
 */
export function OpeningsStrip({
  day,
  loading,
  maxPartySize,
  selectedTime,
  onPick,
  onPickDate,
}: {
  day: DayAvailability | null;
  loading: boolean;
  maxPartySize: number;
  selectedTime: string;
  onPick: (time: string) => void;
  onPickDate: (date: string) => void;
}) {
  const [hover, setHover] = useState<DaySlot | null>(null);

  // A change of the chosen time (click, arrow key, typing) resets the caption to
  // the selected slot rather than a stale hover.
  useEffect(() => setHover(null), [selectedTime]);

  if (!day) {
    return loading ? (
      <div className="h-9 animate-pulse rounded-md bg-slate-100" />
    ) : null;
  }

  const nextOpenLink = day.next_open_date && (
    <button
      type="button"
      onClick={() => onPickDate(day.next_open_date!)}
      className="font-medium text-slate-700 underline hover:text-slate-900"
    >
      {formatDate(day.next_open_date)}
    </button>
  );

  // Non-strip messages ----------------------------------------------------
  if (day.reason === "party_too_large") {
    return (
      <Message tone="amber">
        Parties larger than {maxPartySize} can't be booked here — a manager will
        arrange seating.
      </Message>
    );
  }
  if (day.reason === "closed") {
    return (
      <Message tone="slate">
        Closed that day.{" "}
        {nextOpenLink && <>Next open: {nextOpenLink}.</>}
      </Message>
    );
  }
  if (day.reason === "past") {
    return (
      <Message tone="slate">
        That date has passed. {nextOpenLink && <>Try {nextOpenLink}.</>}
      </Message>
    );
  }

  // Strip (reason === null, or "full" — show the packed night either way) --
  const shown = hover ?? day.slots.find((s) => s.time === selectedTime) ?? null;

  return (
    <div>
      <div className="mb-1 flex text-[10px] text-slate-400">
        {day.slots.map((s) => {
          const onHour = s.time.endsWith(":00");
          const h = Number(s.time.slice(0, 2));
          return (
            <div key={s.time} className="min-w-[14px] flex-1 text-center">
              {onHour ? `${h % 12 === 0 ? 12 : h % 12}${h < 12 ? "a" : "p"}` : ""}
            </div>
          );
        })}
      </div>

      <div className="flex overflow-hidden rounded-md">
        {day.slots.map((s) => (
          <button
            key={s.time}
            type="button"
            disabled={!s.bookable}
            onMouseEnter={() => setHover(s)}
            onMouseLeave={() => setHover(null)}
            onClick={() => onPick(s.time)}
            title={`${formatClock(s.time)} · ${
              s.bookable ? `${s.free_tables} free` : "full"
            }`}
            className={[
              "h-8 min-w-[14px] flex-1 border-r border-white/70 last:border-r-0",
              slotColor(s),
              s.time === selectedTime ? "ring-2 ring-inset ring-slate-900" : "",
              s.bookable ? "cursor-pointer" : "cursor-not-allowed",
            ].join(" ")}
          />
        ))}
      </div>

      <div className="mt-1.5 flex items-center justify-between text-xs">
        <span className="text-slate-600">
          {shown
            ? `${formatClock(shown.time)} · ${
                shown.bookable
                  ? `${shown.free_tables} table${shown.free_tables === 1 ? "" : "s"} free`
                  : "fully booked"
              }`
            : "Hover a slot, or pick a time"}
        </span>
        {day.reason === "full" && nextOpenLink && (
          <span className="text-slate-500">Next opening: {nextOpenLink}</span>
        )}
      </div>
    </div>
  );
}

function slotColor(s: DaySlot): string {
  if (!s.bookable) return "bg-slate-200";
  if (s.free_tables <= 2) return "bg-emerald-200 hover:bg-emerald-300";
  if (s.free_tables <= 5) return "bg-emerald-300 hover:bg-emerald-400";
  return "bg-emerald-400 hover:bg-emerald-500";
}

function Message({
  tone,
  children,
}: {
  tone: "amber" | "slate";
  children: React.ReactNode;
}) {
  const cls =
    tone === "amber"
      ? "bg-amber-50 text-amber-800"
      : "bg-slate-100 text-slate-600";
  return <div className={`rounded-md px-3 py-2 text-sm ${cls}`}>{children}</div>;
}
