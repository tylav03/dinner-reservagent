import { useState } from "react";
import { api, ConflictError, type RestaurantConfig } from "../api";
import { useDayAvailability } from "../hooks";
import { combineDateTimeToIso } from "../lib/time";
import { formatPhoneInput } from "../lib/phone";
import { OpeningsStrip } from "./OpeningsStrip";

interface Props {
  config: RestaurantConfig;
  onCreated: () => void; // tell the parent to refresh the list
  onBooked: (confirmationCode: string) => void; // show the toast, app-level
}

const FIELD_BASE =
  "rounded-md border border-slate-300 py-2 text-sm focus:border-slate-500 focus:outline-none";
const FIELD = `${FIELD_BASE} w-full px-3`;
const FIELD_COMPACT = `${FIELD_BASE} w-full px-2`; // date / time — less padding for the native icon

export function NewReservationForm({ config, onCreated, onBooked }: Props) {
  const [guestName, setGuestName] = useState("");
  const [phone, setPhone] = useState("");
  const [partySize, setPartySize] = useState(2);
  // Date and time start blank — nothing is auto-picked. Filling either one is
  // what reveals the openings strip below.
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [notes, setNotes] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const [reloadKey, setReloadKey] = useState(0); // bump to refetch the strip
  // The hook itself no-ops while `date` is empty, so the strip only ever
  // queries once the host has actually picked a day.
  const { day, loading: dayLoading } = useDayAvailability(date, partySize, reloadKey);

  // A successful booking is announced via a toast (see App.tsx) — it lives on
  // its own timer, not on this form's state, so it can't get stuck once the
  // form moves on. This only needs to clear an in-progress *error*.
  const dismissError = () => setSubmitError(null);

  const editName = (v: string) => {
    setGuestName(v);
    dismissError();
  };
  const editPhone = (v: string) => {
    setPhone(formatPhoneInput(v));
    dismissError();
  };
  const editNotes = (v: string) => {
    setNotes(v);
    dismissError();
  };
  const editParty = (v: number) => {
    setPartySize(v);
    dismissError();
  };
  const editDate = (v: string) => {
    setDate(v);
    dismissError();
  };
  const editTime = (v: string) => {
    setTime(v);
    dismissError();
  };

  const missingSlot = date === "" || time === "";
  const selectedSlot = day?.slots.find((s) => s.time === time) ?? null;
  const slotBlocked =
    missingSlot ||
    (day != null && (day.reason != null || selectedSlot == null || !selectedSlot.bookable));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (submitting || slotBlocked) return; // guards a stray Enter-key submit
    setSubmitting(true);
    dismissError();
    try {
      const r = await api.createReservation({
        guest_name: guestName,
        phone,
        party_size: partySize,
        when: combineDateTimeToIso(date, time),
        notes: notes || null,
        source: "manual",
      });
      onBooked(r.confirmation_code);
      setGuestName("");
      setPhone("");
      setNotes("");
      setReloadKey((k) => k + 1); // the slot just lost a table — refresh the strip
      onCreated();
    } catch (err) {
      if (err instanceof ConflictError) {
        setSubmitError("That opening was just taken — pick another slot.");
        setReloadKey((k) => k + 1);
      } else {
        setSubmitError(String(err));
      }
    } finally {
      setSubmitting(false);
    }
  }

  const canSubmit =
    guestName.trim() !== "" && phone.trim() !== "" && !submitting && !slotBlocked;

  // The button always reads "Create reservation" (or "Booking…" mid-submit) —
  // *why* it's disabled is explained by the openings strip / field state above
  // it, not by relabeling the button itself.
  const buttonLabel = submitting ? "Booking…" : "Create reservation";

  return (
    <form onSubmit={submit} className="space-y-3">
      <div>
        <label className="mb-1 block text-xs font-medium text-slate-600">Guest name</label>
        <input
          className={FIELD}
          value={guestName}
          onChange={(e) => editName(e.target.value)}
          placeholder="Jordan Rivera"
        />
      </div>

      <div>
        <label className="mb-1 block text-xs font-medium text-slate-600">Phone</label>
        <input
          className={FIELD}
          value={phone}
          onChange={(e) => editPhone(e.target.value)}
          placeholder="(212) 555-0123"
          inputMode="tel"
          maxLength={14}
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
          onChange={(e) => editParty(Number(e.target.value))}
        />
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Date</label>
          <input
            type="date"
            className={FIELD_COMPACT}
            value={date}
            onChange={(e) => editDate(e.target.value)}
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Time</label>
          <input
            type="time"
            step={config.slot_granularity_minutes * 60}
            className={FIELD_COMPACT}
            value={time}
            onChange={(e) => editTime(e.target.value)}
          />
        </div>
      </div>

      {date !== "" && (
        <div>
          <div className="mb-1 text-xs font-medium text-slate-600">
            Openings — party of {partySize}
          </div>
          <OpeningsStrip
            day={day}
            loading={dayLoading}
            maxPartySize={config.max_party_size}
            selectedTime={time}
            onPick={(t) => editTime(t)}
            onPickDate={(d) => editDate(d)}
          />
        </div>
      )}

      <div>
        <label className="mb-1 block text-xs font-medium text-slate-600">Notes (optional)</label>
        <input
          className={FIELD}
          value={notes}
          onChange={(e) => editNotes(e.target.value)}
          placeholder="Window table, birthday…"
        />
      </div>

      {/* Only an in-progress error lives here — success is a toast (App.tsx),
          not form state, so it can't linger once you've moved on. */}
      {submitError && (
        <div className="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">{submitError}</div>
      )}

      <button
        type="submit"
        disabled={!canSubmit}
        className="w-full rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-40"
      >
        {buttonLabel}
      </button>
    </form>
  );
}
