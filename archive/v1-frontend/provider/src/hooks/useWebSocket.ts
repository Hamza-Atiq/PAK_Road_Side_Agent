import { useEffect, useRef, useState } from "react";
import { useAuthStore } from "@/store/auth";
import type { WSEvent } from "@/types/api";

type ConnectionStatus = "idle" | "connecting" | "open" | "closed" | "error";

interface Options {
  path: string;
  enabled?: boolean;
  onEvent?: (e: WSEvent) => void;
}

export function useWebSocket({ path, enabled = true, onEvent }: Options) {
  const [status, setStatus] = useState<ConnectionStatus>("idle");
  const [lastEvent, setLastEvent] = useState<WSEvent | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const retryAttemptRef = useRef(0);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    if (!enabled) return;
    const token = useAuthStore.getState().accessToken;
    if (!token) {
      setStatus("error");
      return;
    }
    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      setStatus("connecting");
      const wsBase =
        import.meta.env.VITE_WS_BASE_URL ||
        (location.protocol === "https:" ? "wss" : "ws") + "://" + location.host;
      const url = `${wsBase}${path}?token=${encodeURIComponent(token)}`;
      const ws = new WebSocket(url);
      wsRef.current = ws;
      ws.onopen = () => {
        retryAttemptRef.current = 0;
        setStatus("open");
      };
      ws.onmessage = (msg) => {
        try {
          const ev = JSON.parse(msg.data) as WSEvent;
          setLastEvent(ev);
          onEventRef.current?.(ev);
        } catch { /* ignore */ }
      };
      ws.onerror = () => setStatus("error");
      ws.onclose = (ev) => {
        setStatus("closed");
        wsRef.current = null;
        if (cancelled) return;
        if (ev.code === 1008 || ev.code === 1000) return;
        const delayMs = Math.min(30_000, 1000 * Math.pow(2, retryAttemptRef.current++));
        setTimeout(connect, delayMs);
      };
    };
    connect();

    return () => {
      cancelled = true;
      wsRef.current?.close(1000, "unmount");
      wsRef.current = null;
    };
  }, [path, enabled]);

  return { status, lastEvent };
}
