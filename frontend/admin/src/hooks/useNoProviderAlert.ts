import { useEffect, useState } from "react";
import { incidentsApi } from "@/api/incidents";

/**
 * Global poller for incidents in NO_PROVIDER state.
 *
 * Polls every 15 s. Returns the current count so the NoProviderBanner can
 * decide whether to show. A dedicated poller (separate from any per-page
 * load) means the banner stays accurate even if the admin is on a page that
 * doesn't refetch incidents.
 */
export function useNoProviderAlert() {
  const [count, setCount] = useState(0);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function tick() {
      try {
        const resp = await incidentsApi.list({ status: "NO_PROVIDER", limit: 1 });
        if (!cancelled) {
          setCount(resp.total);
          setLastChecked(new Date());
        }
      } catch {
        // Network/auth blips — just leave the previous count in place.
      }
    }

    tick();
    const t = setInterval(tick, 15_000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, []);

  return { count, lastChecked };
}
