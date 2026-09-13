/**
 * Small data hooks. No data-fetching library — just fetch + setInterval — so the
 * moving parts are visible. In a production app you'd likely reach for TanStack
 * Query (caching, dedupe, retries, stale-while-revalidate) instead of this.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  type DayAvailability,
  type Reservation,
  type RestaurantConfig,
} from "./api";

/** Fetch the restaurant config once on mount. */
export function useConfig() {
  const [config, setConfig] = useState<RestaurantConfig | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getConfig().then(setConfig).catch((e) => setError(String(e)));
  }, []);

  return { config, error };
}

/**
 * Poll one day's reservations on an interval, so a booking made by phone (or in
 * another tab) for that day shows up here within `intervalMs`.
 *
 * @param day  "YYYY-MM-DD" — refetches immediately when it changes.
 */
export function useReservations(day: string, intervalMs = 3000) {
  const [reservations, setReservations] = useState<Reservation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const timer = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await api.listReservations({ day });
      setReservations(data);
      setError(null);
      setLastUpdated(new Date());
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [day]);

  useEffect(() => {
    refresh();
    timer.current = window.setInterval(refresh, intervalMs);
    return () => {
      if (timer.current) window.clearInterval(timer.current);
    };
  }, [refresh, intervalMs]);

  return { reservations, loading, error, lastUpdated, refresh };
}

/**
 * The openings for one day + party size, for the reservation form's strip.
 * Debounced; pass `date = null` to hold off fetching (form not touched yet).
 * Bump `reloadKey` to force a refetch after a booking / conflict.
 */
export function useDayAvailability(
  date: string | null,
  partySize: number,
  reloadKey = 0,
) {
  const [day, setDay] = useState<DayAvailability | null>(null);
  const [loading, setLoading] = useState(false);
  const debounce = useRef<number | null>(null);

  useEffect(() => {
    if (!date || partySize < 1) {
      setDay(null);
      return;
    }
    setLoading(true);
    if (debounce.current) window.clearTimeout(debounce.current);
    debounce.current = window.setTimeout(() => {
      api
        .getDayAvailability(date, partySize)
        .then(setDay)
        .catch(() => setDay(null))
        .finally(() => setLoading(false));
    }, 300);
    return () => {
      if (debounce.current) window.clearTimeout(debounce.current);
    };
  }, [date, partySize, reloadKey]);

  return { day, loading };
}
