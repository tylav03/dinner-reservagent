import type { Availability, AvailabilityReason } from "../api";
import { formatDateTime } from "../lib/time";

const REASON_TEXT: Record<AvailabilityReason, string> = {
  closed: "We're closed then (or too close to closing for a full table turn).",
  party_too_large: "That party is larger than we can seat — a manager would need to help.",
  full: "Fully booked at that time.",
  past: "That time is in the past.",
  beyond_horizon: "That's further ahead than we take bookings.",
  unparseable: "Couldn't understand that date/time.",
};

/**
 * Live feedback under the reservation form: is the chosen slot bookable? If not,
 * shows the reason and clickable alternative times.
 */
export function AvailabilityBadge({
  availability,
  onPickAlternative,
}: {
  availability: Availability | null;
  onPickAlternative: (iso: string) => void;
}) {
  if (!availability) return null;

  if (availability.available) {
    return (
      <div className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
        Available — table <strong>{availability.table_id}</strong> would be assigned.
      </div>
    );
  }

  return (
    <div className="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-800">
      <div>{availability.reason ? REASON_TEXT[availability.reason] : "Not available."}</div>
      {availability.alternatives.length > 0 && (
        <div className="mt-2">
          <div className="text-xs font-medium text-rose-700">Nearest openings:</div>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {availability.alternatives.map((a) => (
              <button
                key={a.when}
                type="button"
                onClick={() => onPickAlternative(a.when)}
                className="rounded border border-rose-300 bg-white px-2 py-1 text-xs text-rose-800 hover:bg-rose-100"
              >
                {formatDateTime(a.when)}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
