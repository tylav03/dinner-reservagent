import { useState } from "react";
import { useConfig, useReservations } from "./hooks";
import { NewReservationForm } from "./components/NewReservationForm";
import { ReservationsList } from "./components/ReservationsList";
import { DayTimeline } from "./components/DayTimeline";
import { todayIsoDate } from "./lib/time";

type Tab = "list" | "floor";

export default function App() {
  const { config, error: configError } = useConfig();
  const { reservations, loading, error, lastUpdated, refresh } = useReservations(3000);
  const [tab, setTab] = useState<Tab>("list");
  const [floorDate, setFloorDate] = useState(todayIsoDate());

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <header className="mb-6 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h1 className="text-2xl font-semibold">{config?.name ?? "Reservations"}</h1>
        {config && (
          <span className="text-sm text-slate-500">
            {config.phone} · turns {config.turn_time_minutes}m · max party {config.max_party_size}
          </span>
        )}
        <span className="ml-auto flex items-center gap-1.5 text-xs text-slate-500">
          <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-emerald-500" />
          live · updated{" "}
          {lastUpdated ? lastUpdated.toLocaleTimeString() : "…"}
        </span>
      </header>

      {configError && (
        <div className="mb-4 rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">
          Can't reach the API at <code>{import.meta.env.VITE_API_BASE ?? "http://localhost:8000"}</code>.
          Is the backend running? ({configError})
        </div>
      )}

      <div className="grid gap-6 md:grid-cols-[320px_1fr]">
        {/* left: create form */}
        <aside className="md:sticky md:top-6 md:self-start">
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
              New reservation
            </h2>
            {config ? (
              <NewReservationForm config={config} onCreated={refresh} />
            ) : (
              <div className="text-sm text-slate-400">Loading…</div>
            )}
          </div>
        </aside>

        {/* right: tabs */}
        <main>
          <div className="mb-3 flex gap-1">
            {(["list", "floor"] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`rounded-md px-3 py-1.5 text-sm font-medium ${
                  tab === t
                    ? "bg-slate-900 text-white"
                    : "bg-white text-slate-600 hover:bg-slate-100"
                }`}
              >
                {t === "list" ? "All reservations" : "Floor by day"}
              </button>
            ))}
            {tab === "floor" && (
              <input
                type="date"
                value={floorDate}
                onChange={(e) => setFloorDate(e.target.value)}
                className="ml-2 rounded-md border border-slate-300 px-2 py-1 text-sm"
              />
            )}
          </div>

          {error && (
            <div className="mb-3 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">
              Refresh failed: {error}
            </div>
          )}
          {loading && <div className="text-sm text-slate-400">Loading reservations…</div>}

          {!loading && tab === "list" && (
            <ReservationsList reservations={reservations} onChanged={refresh} />
          )}
          {!loading && tab === "floor" && config && (
            <DayTimeline reservations={reservations} config={config} date={floorDate} />
          )}
        </main>
      </div>
    </div>
  );
}
