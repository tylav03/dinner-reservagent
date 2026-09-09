import { useMemo } from "react";
import type { Reservation, RestaurantConfig } from "../api";
import { formatTime, hhmmToMinutes, minutesOfDay, weekdayKey } from "../lib/time";

/**
 * Floor view for one day: tables down the side, time across the top, each booking
 * a block spanning its turn time. Built with CSS grid — one column per slot,
 * blocks placed via `grid-column: <start> / span <len>`.
 */
export function DayTimeline({
  reservations,
  config,
  date,
}: {
  reservations: Reservation[];
  config: RestaurantConfig;
  date: string;
}) {
  const windows = config.hours[weekdayKey(date)] ?? [];
  const gran = config.slot_granularity_minutes;
  const turnSlots = Math.round(config.turn_time_minutes / gran);

  const { openMin, slotCount, hourTicks } = useMemo(() => {
    if (windows.length === 0) return { openMin: 0, slotCount: 0, hourTicks: [] as number[] };
    const open = Math.min(...windows.map((w) => hhmmToMinutes(w.open)));
    const close = Math.max(...windows.map((w) => hhmmToMinutes(w.close)));
    const count = Math.round((close - open) / gran);
    const ticks: number[] = [];
    for (let m = Math.ceil(open / 60) * 60; m <= close; m += 60) ticks.push((m - open) / gran);
    return { openMin: open, slotCount: count, hourTicks: ticks };
  }, [windows, gran]);

  if (windows.length === 0) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-8 text-center text-slate-400">
        Closed on this day.
      </div>
    );
  }

  const forDay = reservations.filter(
    (r) => r.start_at.slice(0, 10) === date && r.status === "booked" && r.table_id,
  );
  const byTable = new Map<string, Reservation[]>();
  for (const r of forDay) {
    const list = byTable.get(r.table_id!) ?? [];
    list.push(r);
    byTable.set(r.table_id!, list);
  }

  const cols = `56px repeat(${slotCount}, minmax(14px, 1fr))`;

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <div className="min-w-[720px]">
        {/* header: hour labels */}
        <div className="grid items-end border-b border-slate-200" style={{ gridTemplateColumns: cols }}>
          <div className="px-2 py-1 text-xs font-medium text-slate-400">Table</div>
          {Array.from({ length: slotCount }).map((_, i) => {
            const tick = hourTicks.includes(i);
            return (
              <div
                key={i}
                className={`py-1 text-center text-[10px] text-slate-400 ${
                  tick ? "border-l border-slate-200" : ""
                }`}
              >
                {tick ? formatTime(`T${String(Math.floor((openMin + i * gran) / 60)).padStart(2, "0")}:${String((openMin + i * gran) % 60).padStart(2, "0")}`) : ""}
              </div>
            );
          })}
        </div>

        {/* one row per table */}
        {config.tables.map((t) => (
          <div
            key={t.id}
            className="grid border-b border-slate-100 last:border-0"
            style={{ gridTemplateColumns: cols }}
          >
            <div className="flex items-center gap-1 px-2 py-1.5 text-xs">
              <span className="font-medium">{t.id}</span>
              <span className="text-slate-400">·{t.capacity}</span>
            </div>

            {/* faint hourly gridlines */}
            {Array.from({ length: slotCount }).map((_, i) => (
              <div
                key={i}
                className={hourTicks.includes(i) ? "border-l border-slate-100" : ""}
                style={{ gridColumn: `${i + 2} / span 1`, gridRow: 1 }}
              />
            ))}

            {(byTable.get(t.id) ?? []).map((r) => {
              const startSlot = Math.round((minutesOfDay(r.start_at) - openMin) / gran);
              const isVoice = r.source === "voice";
              return (
                <div
                  key={r.id}
                  title={`${r.guest_name} · party ${r.party_size} · ${formatTime(
                    r.start_at,
                  )}–${formatTime(r.end_at)} · ${r.confirmation_code}`}
                  className={`m-0.5 overflow-hidden rounded px-1.5 py-1 text-[11px] leading-tight text-white ${
                    isVoice ? "bg-indigo-500" : "bg-slate-500"
                  }`}
                  style={{
                    gridColumn: `${startSlot + 2} / span ${turnSlots}`,
                    gridRow: 1,
                  }}
                >
                  <span className="font-medium">{r.guest_name.split(" ").at(-1)}</span>{" "}
                  <span className="opacity-80">{r.party_size}p</span>
                </div>
              );
            })}
          </div>
        ))}
      </div>

      <div className="flex gap-4 px-3 py-2 text-xs text-slate-500">
        <span className="flex items-center gap-1">
          <span className="inline-block h-3 w-3 rounded bg-indigo-500" /> booked by voice agent
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-3 w-3 rounded bg-slate-500" /> booked manually / API
        </span>
      </div>
    </div>
  );
}
