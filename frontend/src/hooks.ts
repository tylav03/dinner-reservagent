/**
 * Small data hooks. No data-fetching library — just fetch + setInterval — so the
 * moving parts are visible. In a production app you'd likely reach for TanStack
 * Query (caching, dedupe, retries, stale-while-revalidate) instead of this.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Reservation, type RestaurantConfig } from "./api";

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
 * Poll the reservation list on an interval so a booking made by phone (or in
 * another tab) shows up here within `intervalMs`.
 */
export function useReservations(intervalMs = 3000) {
  const [reservations, setReservations] = useState<Reservation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const timer = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await api.listReservations();
      setReservations(data);
      setError(null);
      setLastUpdated(new Date());
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    timer.current = window.setInterval(refresh, intervalMs);
    return () => {
      if (timer.current) window.clearInterval(timer.current);
    };
  }, [refresh, intervalMs]);

  return { reservations, loading, error, lastUpdated, refresh };
}
