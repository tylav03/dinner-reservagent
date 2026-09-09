import { useMemo, useState } from "react";
import { api, type Reservation } from "../api";
import { formatDate, formatTime } from "../lib/time";
import { SourceBadge, StatusPill } from "./StatusPill";

type SortKey = "when" | "guest" | "party";

export function ReservationsList({
  reservations,
  onChanged,
}: {
  reservations: Reservation[];
  onChanged: () => void;
}) {
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "when", dir: 1 });
  const [hideCancelled, setHideCancelled] = useState(true);
  const [q, setQ] = useState("");

  const rows = useMemo(() => {
    let r = [...reservations];
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
    r.sort((a, b) => {
      let cmp = 0;
      if (sort.key === "when") cmp = a.start_at.localeCompare(b.start_at);
      else if (sort.key === "guest") cmp = a.guest_name.localeCompare(b.guest_name);
      else cmp = a.party_size - b.party_size;
      return cmp * sort.dir;
    });
    return r;
  }, [reservations, sort, hideCancelled, q]);

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
        <span className="ml-auto text-sm text-slate-500">{rows.length} shown</span>
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
            {rows.map((r) => (
              <tr key={r.id} className="hover:bg-slate-50">
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
                      onClick={() => cancel(r.confirmation_code)}
                      className="text-xs text-rose-600 hover:underline"
                    >
                      Cancel
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-slate-400">
                  No reservations.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
