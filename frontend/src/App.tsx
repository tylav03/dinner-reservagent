import { useCallback, useState } from "react";
import { useConfig, useReservations } from "./hooks";
import { NewReservationForm } from "./components/NewReservationForm";
import { ReservationsList } from "./components/ReservationsList";
import { DayTimeline } from "./components/DayTimeline";
import { Toast, type ToastMessage } from "./components/Toast";
import { addDaysToIsoDate, formatDate, todayIsoDate } from "./lib/time";

type Tab = "list" | "floor";

export default function App() {
  const { config, error: configError } = useConfig();
  const [selectedDate, setSelectedDate] = useState(todayIsoDate());
  const { reservations, loading, error, lastUpdated, refresh } = useReservations(selectedDate);
  const [tab, setTab] = useState<Tab>("list");

  // App-level, not form/list state: a confirmation toast should outlive
  // whatever triggered it and show no matter which tab is open. Both booking
  // and cancelling report through this one function.
  const [toast, setToast] = useState<ToastMessage | null>(null);
  const showToast = useCallback((text: string) => setToast({ id: Date.now(), text }), []);
  // Stable identity: the reservation list polls every 3s and re-renders App,
  // and Toast's auto-dismiss timer resets whenever `onDismiss` changes — an
  // inline arrow here would recreate it every poll and the toast would never
  // survive long enough to time out.
  const dismissToast = useCallback(() => setToast(null), []);

  const isToday = selectedDate === todayIsoDate();

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
          live · updated {lastUpdated ? lastUpdated.toLocaleTimeString() : "…"}
        </span>
      </header>

      {configError && (
        <div className="mb-4 rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">
          Can't reach the API at{" "}
          <code>{import.meta.env.VITE_API_BASE ?? "http://localhost:8000"}</code>. Is the backend
          running? ({configError})
        </div>
      )}

      <div className="grid gap-6 md:grid-cols-[340px_1fr]">
        {/* left: create form */}
        <aside className="md:sticky md:top-6 md:self-start">
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
              New reservation
            </h2>
            {config ? (
              <NewReservationForm
                config={config}
                onCreated={refresh}
                onBooked={(code) => showToast(`Booked — confirmation ${code}`)}
              />
            ) : (
              <div className="text-sm text-slate-400">Loading…</div>
            )}
          </div>
        </aside>

        {/* right: day view */}
        <main>
          {/* date navigation — drives both tabs */}
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <button
              onClick={() => setSelectedDate(addDaysToIsoDate(selectedDate, -1))}
              className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm hover:bg-slate-100"
              aria-label="Previous day"
            >
              ◀
            </button>
            <input
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="rounded-md border border-slate-300 px-2 py-1 text-sm"
            />
            <button
              onClick={() => setSelectedDate(addDaysToIsoDate(selectedDate, 1))}
              className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm hover:bg-slate-100"
              aria-label="Next day"
            >
              ▶
            </button>
            <button
              onClick={() => setSelectedDate(todayIsoDate())}
              disabled={isToday}
              className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm hover:bg-slate-100 disabled:opacity-40"
            >
              Today
            </button>
            <span className="ml-1 text-sm font-medium text-slate-700">
              {formatDate(selectedDate)}
              {isToday && <span className="ml-1 text-slate-400">(today)</span>}
            </span>

            <div className="ml-auto flex gap-1">
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
                  {t === "list" ? "Reservations" : "Floor"}
                </button>
              ))}
            </div>
          </div>

          {error && (
            <div className="mb-3 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">
              Refresh failed: {error}
            </div>
          )}
          {loading && <div className="text-sm text-slate-400">Loading reservations…</div>}

          {!loading && tab === "list" && (
            <ReservationsList
              reservations={reservations}
              date={selectedDate}
              onChanged={refresh}
              onCancelled={(code) => showToast(`Cancelled — confirmation ${code}`)}
            />
          )}
          {!loading && tab === "floor" && config && (
            <DayTimeline reservations={reservations} config={config} date={selectedDate} />
          )}
        </main>
      </div>

      <Toast message={toast} onDismiss={dismissToast} />
    </div>
  );
}
