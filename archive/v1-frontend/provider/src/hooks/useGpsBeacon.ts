// useGpsBeacon — background GPS pinger.
//
// Calls `navigator.geolocation.watchPosition` (more battery-friendly than
// polling) and forwards each fix to the backend at most once per `intervalMs`.
// Stops automatically when `enabled` flips to false or the component unmounts.

import { useEffect, useRef, useState } from "react";
import { providersApi } from "@/api/providers";

interface Options {
  enabled: boolean;
  intervalMs?: number;
  onError?: (msg: string) => void;
}

interface State {
  lastPingAt: string | null;
  lastLat: number | null;
  lastLng: number | null;
  inFlight: boolean;
  error: string | null;
}

export function useGpsBeacon({
  enabled,
  intervalMs = 30_000,
  onError,
}: Options) {
  const [state, setState] = useState<State>({
    lastPingAt: null,
    lastLat: null,
    lastLng: null,
    inFlight: false,
    error: null,
  });
  const watchIdRef = useRef<number | null>(null);
  const lastSentAtRef = useRef<number>(0);

  useEffect(() => {
    if (!enabled) return;
    if (!("geolocation" in navigator)) {
      const msg = "Geolocation not supported";
      setState((s) => ({ ...s, error: msg }));
      onError?.(msg);
      return;
    }

    const send = async (lat: number, lng: number) => {
      setState((s) => ({ ...s, inFlight: true }));
      try {
        const result = await providersApi.pingLocation(lat, lng);
        setState({
          lastPingAt: result.last_ping,
          lastLat: lat,
          lastLng: lng,
          inFlight: false,
          error: null,
        });
      } catch (err: any) {
        const msg = err?.response?.data?.detail || err?.message || "ping failed";
        setState((s) => ({ ...s, inFlight: false, error: msg }));
        onError?.(msg);
      }
    };

    const id = navigator.geolocation.watchPosition(
      (pos) => {
        const now = Date.now();
        if (now - lastSentAtRef.current < intervalMs) return;
        lastSentAtRef.current = now;
        void send(pos.coords.latitude, pos.coords.longitude);
      },
      (err) => {
        const msg = err.message || "GPS error";
        setState((s) => ({ ...s, error: msg }));
        onError?.(msg);
      },
      { enableHighAccuracy: true, maximumAge: 10_000, timeout: 15_000 }
    );
    watchIdRef.current = id;

    return () => {
      if (watchIdRef.current != null) {
        navigator.geolocation.clearWatch(watchIdRef.current);
      }
      watchIdRef.current = null;
    };
  }, [enabled, intervalMs, onError]);

  return state;
}
