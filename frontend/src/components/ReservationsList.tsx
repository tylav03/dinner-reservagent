import { useEffect, useMemo, useState } from "react";
import { api, type Reservation } from "../api";
import { formatDate, formatTime, nowLocalIso } from "../lib/time";
import { SourceBadge, StatusPill } from "./StatusPill";

type SortKey = "when" | "guest" | "party";

export function ReservationsList({
  reservations,
  date,
  onChanged,
}: {
  reservations: Reservation[];
  date: string; // "YYYY-MM-DD" currently in view
  onChanged: () => void;
}) {
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "when", dir: 1 });
  const [hideCancelled, setHideCancelled] = useState(true);
  const [q, setQ] = useState("");
  const [showHistory, setShowHistory] = useState(false);

  // A fresh day starts with history collapsed again.
  useEffect(() => setShowHistory(false), [date]);

  const { upcoming, past } = useMemo(() => {
    const now = nowLocalIso();
    let r = reservations.filter((x) => x.start_at.slice(0, 10) === date);
    if (hideCancelled) r = r.filter((x) => x.status !== "cancelled");
    if (q.trim()) {
      const s = q.trim().toLowerCase();
      r = r.filter(
        (x) =>
          x.guest_name.toLowerCase().includes(s) ||
          x.phone.toLowerCase().includes(s) ||
          x.confirmation_code.toLowerCase().includes(s),
      );
    }
    const cmp = (a: Reservation, b: Reservation) => {
      let c = 0;
      if (sort.key === "when") c = a.start_at.localeCompare(b.start_at);
      else if (sort.key === "guest") c = a.guest_name.localeCompare(b.guest_name);
      else c = a.party_size - b.party_size;
      return c * sort.dir;
    };
    return {
      // "past" = the table's turn has already ended
      upcoming: r.filter((x) => x.end_at > now).sort(cmp),
      past: r.filter((x) => x.end_at <= now).sort(cmp),
    };
  }, [reservations, date, sort, hideCancelled, q]);

  const hasUpcoming = upcoming.length > 0;
  const hasPast = past.length > 0;
  // If there's nothing current to show, just reveal the past (greyed) rather than
  // showing an empty table behind a button.
  const historyShown = showHistory || !hasUpcoming;

  function toggleSort(key: SortKey) {
    setSort((s) => (s.key === key ? { key, dir: (s.dir * -1) as 1 | -1 } : { key, dir: 1 }));
  }

  async function cancel(code: string) {
    await api.cancelReservation(code);
    onChanged();
  }

  const arrow = (key: SortKey) => (sort.key === key ? (sort.dir === 1 ? " ▲" : " ▼") : "");

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search name, phone, code…"
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none"
        />
        <label className="flex items-center gap-1.5 text-sm text-slate-600">
          <input
            type="checkbox"
            checked={hideCancelled}
            onChange={(e) => setHideCancelled(e.target.checked)}
          />
          Hide cancelled
        </label>
        <span className="ml-auto text-sm text-slate-500">
          {hasUpcoming ? `${upcoming.length} upcoming` : "none upcoming"}
          {hasPast && ` · ${past.length} past`}
        </span>
      </div>

      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="cursor-pointer px-3 py-2" onClick={() => toggleSort("when")}>
                When{arrow("when")}
              </th>
              <th className="cursor-pointer px-3 py-2" onClick={() => toggleSort("guest")}>
                Guest{arrow("guest")}
              </th>
              <th className="cursor-pointer px-3 py-2" onClick={() => toggleSort("party")}>
                Party{arrow("party")}
              </th>
              <th className="px-3 py-2">Table</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Source</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {upcoming.map((r) => (
              <Row key={r.id} r={r} onCancel={cancel} />
            ))}

            {!hasUpcoming && !hasPast && (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-slate-400">
                  No reservations for {formatDate(date)}.
                </td>
              </tr>
            )}

            {/* history */}
            {hasPast && hasUpcoming && (
              <tr>
                <td colSpan={7} className="bg-slate-50 px-3 py-1.5">
                  <button
                    onClick={() => setShowHistory((v) => !v)}
                    className="text-xs font-medium text-slate-500 hover:text-slate-700"
                  >
                    {showHistory ? "▾ Hide history" : `▸ Show history (${past.length})`}
                  </button>
                </td>
              </tr>
            )}
            {hasPast && !hasUpcoming && (
              <tr>
                <td colSpan={7} className="bg-slate-50 px-3 py-1.5 text-xs text-slate-400">
                  These reservations have already passed.
                </td>
              </tr>
            )}
            {hasPast &&
              historyShown &&
              past.map((r) => <Row key={r.id} r={r} onCancel={cancel} dim />)}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Row({
  r,
  onCancel,
  dim = false,
}: {
  r: Reservation;
  onCancel: (code: string) => void;
  dim?: boolean;
}) {
  return (
    <tr className={`hover:bg-slate-50 ${dim ? "opacity-60" : ""}`}>
      <td className="whitespace-nowrap px-3 py-2">
        <div className="font-medium">{formatDate(r.start_at)}</div>
        <div className="text-slate-500">{formatTime(r.start_at)}</div>
      </td>
      <td className="px-3 py-2">
        <div className="font-medium">{r.guest_name}</div>
        <div className="text-xs text-slate-500">
          {r.phone} · {r.confirmation_code}
        </div>
        {r.notes && <div className="text-xs italic text-slate-400">{r.notes}</div>}
      </td>
      <td className="px-3 py-2">{r.party_size}</td>
      <td className="px-3 py-2">{r.table_id ?? "—"}</td>
      <td className="px-3 py-2">
        <StatusPill status={r.status} />
      </td>
      <td className="px-3 py-2">
        <SourceBadge source={r.source} />
      </td>
      <td className="px-3 py-2 text-right">
        {r.status === "booked" && (
          <button
            onClick={() => onCancel(r.confirmation_code)}
            className="text-xs text-rose-600 hover:underline"
          >
            Cancel
          </button>
        )}
      </td>
    </tr>
  );
}
