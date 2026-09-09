import { useEffect, useRef, useState } from "react";
import {
  api,
  ConflictError,
  type Availability,
  type RestaurantConfig,
} from "../api";
import { combineDateTimeToIso, isoDateOffset } from "../lib/time";
import { AvailabilityBadge } from "./AvailabilityBadge";

interface Props {
  config: RestaurantConfig;
  onCreated: () => void; // tell the parent to refresh the list
}

const FIELD_BASE =
  "rounded-md border border-slate-300 py-2 text-sm focus:border-slate-500 focus:outline-none";
const FIELD = `${FIELD_BASE} w-full px-3`; // full-width text inputs
const FIELD_COMPACT = `${FIELD_BASE} w-full px-2`; // date / time — less side padding for the native icon

export function NewReservationForm({ config, onCreated }: Props) {
  const [guestName, setGuestName] = useState("");
  const [phone, setPhone] = useState("");
  const [partySize, setPartySize] = useState(2);
  const [date, setDate] = useState(isoDateOffset(1)); // default to tomorrow
  const [time, setTime] = useState("19:00");
  const [notes, setNotes] = useState("");

  const [availability, setAvailability] = useState<Availability | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [justBooked, setJustBooked] = useState<string | null>(null);

  // The availability check is only meaningful once the user has expressed intent
  // about *when* / *how many*. Until then the form is pristine and we show no
  // banner (a banner implies something happened).
  const [slotTouched, setSlotTouched] = useState(false);
  const markSlotTouched = () => setSlotTouched(true);

  const whenIso = combineDateTimeToIso(date, time);

  // Debounced live availability check — skipped entirely until a when/party field
  // has been touched.
  const debounce = useRef<number | null>(null);
  useEffect(() => {
    if (!slotTouched) return;
    if (debounce.current) window.clearTimeout(debounce.current);
    debounce.current = window.setTimeout(() => {
      api
        .getAvailability(whenIso, partySize)
        .then(setAvailability)
        .catch(() => setAvailability(null));
    }, 400);
    return () => {
      if (debounce.current) window.clearTimeout(debounce.current);
    };
  }, [whenIso, partySize, slotTouched]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setSubmitError(null);
    setJustBooked(null);
    try {
      const r = await api.createReservation({
        guest_name: guestName,
        phone,
        party_size: partySize,
        when: whenIso,
        notes: notes || null,
      });
      setJustBooked(r.confirmation_code);
      setGuestName("");
      setPhone("");
      setNotes("");
      setAvailability(null); // clear the pre-booking check; the success banner stands alone
      setSlotTouched(false);
      onCreated();
    } catch (err) {
      if (err instanceof ConflictError) {
        setSlotTouched(true);
        setAvailability(err.detail); // show reason + alternatives
        setSubmitError("That slot isn't available — see below.");
      } else {
        setSubmitError(String(err));
      }
    } finally {
      setSubmitting(false);
    }
  }

  const canSubmit = guestName.trim() && phone.trim() && partySize > 0 && !submitting;

  return (
    <form onSubmit={submit} className="space-y-3">
      <div>
        <label className="mb-1 block text-xs font-medium text-slate-600">Guest name</label>
        <input
          className={FIELD}
          value={guestName}
          onChange={(e) => setGuestName(e.target.value)}
          placeholder="Jordan Rivera"
        />
      </div>

      <div>
        <label className="mb-1 block text-xs font-medium text-slate-600">Phone</label>
        <input
          className={FIELD}
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          placeholder="(212) 555-0123"
        />
      </div>

      <div>
        <label className="mb-1 block text-xs font-medium text-slate-600">Party size</label>
        <input
          type="number"
          min={1}
          max={config.max_party_size + 4}
          className={`${FIELD_BASE} w-24 px-3`}
          value={partySize}
          onChange={(e) => {
            setPartySize(Number(e.target.value));
            markSlotTouched();
          }}
        />
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Date</label>
          <input
            type="date"
            className={FIELD_COMPACT}
            value={date}
            onChange={(e) => {
              setDate(e.target.value);
              markSlotTouched();
            }}
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Time</label>
          <input
            type="time"
            step={config.slot_granularity_minutes * 60}
            className={FIELD_COMPACT}
            value={time}
            onChange={(e) => {
              setTime(e.target.value);
              markSlotTouched();
            }}
          />
        </div>
      </div>

      <div>
        <label className="mb-1 block text-xs font-medium text-slate-600">Notes (optional)</label>
        <input
          className={FIELD}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Window table, birthday…"
        />
      </div>

      {slotTouched && (
        <AvailabilityBadge
          availability={availability}
          onPickAlternative={(iso) => {
            const [d, t] = iso.split("T");
            setDate(d);
            setTime(t.slice(0, 5));
          }}
        />
      )}

      {submitError && <div className="text-sm text-rose-700">{submitError}</div>}
      {justBooked && (
        <div className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
          Booked — confirmation <strong>{justBooked}</strong>.
        </div>
      )}

      <button
        type="submit"
        disabled={!canSubmit}
        className="w-full rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-40"
      >
        {submitting ? "Booking…" : "Create reservation"}
      </button>
    </form>
  );
}
