/**
 * Time helpers. The backend speaks naive local ISO strings like
 * "2026-08-28T19:00:00" (no timezone). We treat them as wall-clock time and
 * never involve `Date` timezone math beyond parsing the parts.
 */

/** "2026-08-28" + "19:00" -> "2026-08-28T19:00:00" */
export function combineDateTimeToIso(date: string, time: string): string {
  return `${date}T${time.length === 5 ? `${time}:00` : time}`;
}

/** Parse "2026-08-28T19:00:00" into its numeric parts without timezone shifts. */
function parts(iso: string) {
  const [d, t = "00:00:00"] = iso.split("T");
  const [y, mo, day] = d.split("-").map(Number);
  const [h, mi] = t.split(":").map(Number);
  return { y, mo, day, h, mi };
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export function formatTime(iso: string): string {
  const { h, mi } = parts(iso);
  const am = h < 12;
  const h12 = h % 12 === 0 ? 12 : h % 12;
  return `${h12}:${String(mi).padStart(2, "0")} ${am ? "AM" : "PM"}`;
}

export function formatDate(iso: string): string {
  const { y, mo, day } = parts(iso);
  const wd = new Date(y, mo - 1, day).getDay();
  return `${WEEKDAYS[wd]}, ${MONTHS[mo - 1]} ${day}`;
}

export function formatDateTime(iso: string): string {
  return `${formatDate(iso)} · ${formatTime(iso)}`;
}

/** Minutes from midnight for the time part of an ISO string. */
export function minutesOfDay(iso: string): number {
  const { h, mi } = parts(iso);
  return h * 60 + mi;
}

/** "HH:MM" -> minutes from midnight. */
export function hhmmToMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number);
  return h * 60 + m;
}

/** A date `offsetDays` from today as "YYYY-MM-DD" in the browser's local time. */
export function isoDateOffset(offsetDays = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate(),
  ).padStart(2, "0")}`;
}

export function todayIsoDate(): string {
  return isoDateOffset(0);
}

/** Current local wall-clock time as "YYYY-MM-DDTHH:MM:SS" — comparable as a
 *  string against the backend's naive-local `start_at` / `end_at`. */
export function nowLocalIso(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return (
    `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}` +
    `T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
  );
}

/** "2026-09-09" + n days -> "YYYY-MM-DD". Handles month/year rollover. */
export function addDaysToIsoDate(isoDate: string, n: number): string {
  const [y, m, d] = isoDate.split("-").map(Number);
  const dt = new Date(y, m - 1, d + n);
  const p = (x: number) => String(x).padStart(2, "0");
  return `${dt.getFullYear()}-${p(dt.getMonth() + 1)}-${p(dt.getDate())}`;
}

/** JS weekday (0=Sun) -> backend key ("mon".."sun"). */
export function weekdayKey(isoDate: string): string {
  const [y, mo, day] = isoDate.split("-").map(Number);
  const jsDay = new Date(y, mo - 1, day).getDay(); // 0=Sun
  return ["sun", "mon", "tue", "wed", "thu", "fri", "sat"][jsDay];
}
