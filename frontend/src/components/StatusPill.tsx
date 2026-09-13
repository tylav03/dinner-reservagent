import type { ReservationStatus } from "../api";

const STYLES: Record<ReservationStatus, string> = {
  booked: "bg-emerald-100 text-emerald-800",
  seated: "bg-blue-100 text-blue-800",
  completed: "bg-slate-200 text-slate-700",
  cancelled: "bg-rose-100 text-rose-700",
  no_show: "bg-amber-100 text-amber-800",
};

export function StatusPill({ status }: { status: ReservationStatus }) {
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${STYLES[status]}`}
    >
      {status.replace("_", " ")}
    </span>
  );
}

export function SourceBadge({ source }: { source: "voice" | "manual" | "api" }) {
  const label = source === "api" ? "API" : source; // "voice" | "manual" | "API"
  return <span className="text-xs text-slate-500">{label}</span>;
}
