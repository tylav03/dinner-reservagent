/**
 * Typed client for the reservation API (FastAPI backend from Phase 1).
 *
 * The shapes here mirror `app/reservations/schemas.py`. If the backend schema
 * changes, update these types too — there's no codegen in this demo.
 */

const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

// --- wire types -----------------------------------------------------------

export type ReservationStatus =
  | "booked"
  | "seated"
  | "completed"
  | "cancelled"
  | "no_show";

export interface Reservation {
  id: string;
  confirmation_code: string;
  guest_name: string;
  phone: string;
  party_size: number;
  start_at: string; // naive local ISO, e.g. "2026-08-28T19:00:00"
  end_at: string;
  table_id: string | null;
  status: ReservationStatus;
  source: "voice" | "manual" | "api";
  notes: string | null;
}

export type AvailabilityReason =
  | "closed"
  | "party_too_large"
  | "full"
  | "past"
  | "beyond_horizon"
  | "unparseable";

export interface Availability {
  available: boolean;
  requested: string;
  party_size: number;
  table_id: string | null;
  reason: AvailabilityReason | null;
  alternatives: { when: string }[];
}

export interface DaySlot {
  time: string; // "HH:MM"
  free_tables: number;
  bookable: boolean;
}

export interface DayAvailability {
  date: string; // "YYYY-MM-DD"
  party_size: number;
  slot_minutes: number;
  windows: { open: string; close: string }[]; // [] when closed
  reason: AvailabilityReason | null; // null when the day has openings
  next_open_date: string | null;
  slots: DaySlot[];
}

export interface RestaurantConfig {
  name: string;
  timezone: string;
  phone: string;
  address: string;
  turn_time_minutes: number;
  slot_granularity_minutes: number;
  max_party_size: number;
  booking_horizon_days: number;
  hours: Record<string, { open: string; close: string }[]>; // "mon" -> windows
  tables: { id: string; capacity: number; section: string }[];
}

export interface CreateReservationBody {
  guest_name: string;
  phone: string;
  party_size: number;
  when: string; // ISO datetime or free text
  notes?: string | null;
  idempotency_key?: string | null;
  source?: "manual" | "api" | "voice"; // defaults to "manual" server-side
}

// --- error type ---------------------------------------------------------

/** Thrown on a 409 from POST /reservations. Carries the availability detail so
 *  the UI can show the reason and offer alternative slots. */
export class ConflictError extends Error {
  constructor(public detail: Availability) {
    super(detail.reason ?? "conflict");
    this.name = "ConflictError";
  }
}

// --- low-level fetch --------------------------------------------------------

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });

  if (res.status === 409) {
    const body = await res.json();
    throw new ConflictError(body.detail as Availability);
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// --- endpoints -----------------------------------------------------------

export const api = {
  getConfig: () => request<RestaurantConfig>("/api/config"),

  listReservations: (params?: { day?: string; upcoming?: boolean }) => {
    const q = new URLSearchParams();
    if (params?.day) q.set("day", params.day);
    if (params?.upcoming) q.set("upcoming", "true");
    const qs = q.toString();
    return request<Reservation[]>(`/api/reservations${qs ? `?${qs}` : ""}`);
  },

  getAvailability: (whenIso: string, partySize: number) => {
    const q = new URLSearchParams({
      when: whenIso,
      party_size: String(partySize),
    });
    return request<Availability>(`/api/availability?${q}`);
  },

  getDayAvailability: (date: string, partySize: number) => {
    const q = new URLSearchParams({ date, party_size: String(partySize) });
    return request<DayAvailability>(`/api/availability/day?${q}`);
  },

  createReservation: (body: CreateReservationBody) =>
    request<Reservation>("/api/reservations", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  cancelReservation: (code: string) =>
    request<Reservation>(`/api/reservations/${code}`, { method: "DELETE" }),

  patchReservation: (
    code: string,
    body: { status?: ReservationStatus; notes?: string },
  ) =>
    request<Reservation>(`/api/reservations/${code}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
};
