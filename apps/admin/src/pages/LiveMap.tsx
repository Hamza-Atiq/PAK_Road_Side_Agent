import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import { incidentsApi } from "@/api/incidents";
import { providersApi } from "@/api/providers";
import { useWebSocket } from "@/hooks/useWebSocket";
import { StatusPill } from "@/components/StatusPill";
import type {
  IncidentBrief,
  IncidentStatus,
  ProviderListItem,
  WSEvent,
} from "@/types/api";

// Incident statuses that aren't yet finished — these are the only ones we
// show on the map. Terminal states (COMPLETED, CLOSED) are excluded.
const OPEN_STATUSES: IncidentStatus[] = [
  "REPORTED", "ANALYZING", "ASSIGNED",
  "NO_PROVIDER", "ESCALATED",
  "EN_ROUTE", "ARRIVED",
];

const STATUS_COLOR: Record<string, string> = {
  REPORTED:    "#64748b", // slate
  ANALYZING:   "#0284c7", // sky
  ASSIGNED:    "#4f46e5", // indigo
  NO_PROVIDER: "#e11d48", // rose (alert)
  ESCALATED:   "#ea580c", // orange (alert)
  EN_ROUTE:    "#d97706", // amber
  ARRIVED:     "#7c3aed", // violet
};

function incidentIcon(status: string) {
  const color = STATUS_COLOR[status] || "#64748b";
  return L.divIcon({
    className: "",
    html: `<div style="
      width:22px;height:22px;border-radius:50%;
      background:${color};
      border:3px solid #fff;
      box-shadow:0 1px 4px rgba(0,0,0,0.4)
    "></div>`,
    iconSize: [22, 22],
    iconAnchor: [11, 11],
  });
}

function providerIcon(state: "available" | "on_job" | "offline") {
  const color =
    state === "available" ? "#059669" :
    state === "on_job"    ? "#2563eb" : "#94a3b8";
  // Square so providers visually differ from circular incidents
  return L.divIcon({
    className: "",
    html: `<div style="
      width:16px;height:16px;
      background:${color};
      border:2px solid #fff;
      box-shadow:0 1px 3px rgba(0,0,0,0.35)
    "></div>`,
    iconSize: [16, 16],
    iconAnchor: [8, 8],
  });
}

interface ProviderMarker {
  id: string;
  name: string;
  service_type: string;
  is_available: boolean;
  lat: number;
  lng: number;
  on_job: boolean;
  last_seen: string;
}

// Default view: roughly centered over the seed data (San Francisco). Falls
// back to a world-ish view if no data ever arrives.
const DEFAULT_CENTER: [number, number] = [37.7749, -122.4194];

function FitOnce({ points }: { points: [number, number][] }) {
  const map = useMap();
  const didFit = useRef(false);
  useEffect(() => {
    if (didFit.current) return;
    if (points.length === 0) return;
    if (points.length === 1) {
      map.setView(points[0], 13);
    } else {
      map.fitBounds(L.latLngBounds(points.map((p) => L.latLng(p[0], p[1]))), {
        padding: [50, 50],
      });
    }
    didFit.current = true;
  }, [map, points]);
  return null;
}

export function LiveMap() {
  const [incidents, setIncidents] = useState<IncidentBrief[]>([]);
  const [providers, setProviders] = useState<Record<string, ProviderMarker>>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const lastEventAt = useRef<Date | null>(null);
  const [eventTick, setEventTick] = useState(0);

  const refetch = useCallback(async () => {
    try {
      // Run two list calls in parallel: NO_PROVIDER+ESCALATED count under the
      // "open" set, so we just fetch a wide page of incidents and filter.
      const [incidentsResp, providersResp] = await Promise.all([
        incidentsApi.list({ limit: 200 }),
        providersApi.list({ is_approved: true }),
      ]);
      const open = incidentsResp.items.filter((i) =>
        OPEN_STATUSES.includes(i.status as IncidentStatus)
      );
      setIncidents(open);

      const onJobProviderIds = new Set(
        open.filter((i) => i.provider_id).map((i) => i.provider_id as string)
      );
      const dict: Record<string, ProviderMarker> = {};
      for (const p of providersResp.items) {
        dict[p.id] = providerMarkerFromList(p, onJobProviderIds.has(p.id));
      }
      // Carry over any previously-seen GPS coords for providers the API list
      // doesn't include yet (e.g. just-now-pinged providers).
      setProviders((prev) => {
        const merged: Record<string, ProviderMarker> = { ...dict };
        for (const [id, prevMarker] of Object.entries(prev)) {
          if (merged[id]) {
            // Prefer the most recent of the two coordinate sources
            const a = new Date(merged[id].last_seen).getTime();
            const b = new Date(prevMarker.last_seen).getTime();
            if (b > a && prevMarker.lat !== 0) {
              merged[id] = { ...merged[id], lat: prevMarker.lat, lng: prevMarker.lng, last_seen: prevMarker.last_seen };
            }
          } else if (prevMarker.lat !== 0) {
            merged[id] = prevMarker;
          }
        }
        return merged;
      });
      setError(null);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Could not load live data.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refetch();
    const t = setInterval(refetch, 20_000);
    return () => clearInterval(t);
  }, [refetch]);

  // WebSocket subscription to the admin firehose: every incident event +
  // PROVIDER_LOCATION pings from the providers API.
  const onEvent = useCallback((ev: WSEvent) => {
    lastEventAt.current = new Date();
    setEventTick((t) => t + 1);

    if (ev.event === "PROVIDER_LOCATION" && ev.data) {
      const d = ev.data as { provider_id?: string; lat?: number; lng?: number; is_available?: boolean };
      if (!d.provider_id || typeof d.lat !== "number" || typeof d.lng !== "number") return;
      setProviders((prev) => {
        const existing = prev[d.provider_id!];
        return {
          ...prev,
          [d.provider_id!]: {
            id: d.provider_id!,
            name: existing?.name ?? "Provider",
            service_type: existing?.service_type ?? "—",
            is_available: d.is_available ?? existing?.is_available ?? false,
            on_job: existing?.on_job ?? false,
            lat: d.lat!,
            lng: d.lng!,
            last_seen: new Date().toISOString(),
          },
        };
      });
      return;
    }

    // Incident lifecycle events → just refetch. Cheap enough for a few
    // hundred rows and avoids subtle merge bugs.
    if (
      ev.event === "INCIDENT_CREATED" ||
      ev.event === "STATUS_CHANGED" ||
      ev.event === "ASSIGNED" ||
      ev.event === "NO_PROVIDER"
    ) {
      void refetch();
    }
  }, [refetch]);

  const ws = useWebSocket({ path: "/ws/admin/live", onEvent });

  const points = useMemo<[number, number][]>(() => {
    const list: [number, number][] = incidents.map((i) => [i.lat, i.lng]);
    for (const p of Object.values(providers)) {
      if (p.lat !== 0 || p.lng !== 0) list.push([p.lat, p.lng]);
    }
    return list;
  }, [incidents, providers]);

  return (
    <div className="space-y-3">
      <header className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Live operations map</h1>
          <p className="text-sm text-slate-500">
            {incidents.length} open incident{incidents.length === 1 ? "" : "s"}
            {" · "}
            {Object.values(providers).filter((p) => p.is_available && !p.on_job).length} providers available
            {" · "}
            {Object.values(providers).filter((p) => p.on_job).length} on job
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ConnectionDot status={ws.status} eventTick={eventTick} />
          <button onClick={() => void refetch()} className="btn-secondary text-sm">
            Refresh
          </button>
        </div>
      </header>

      {error && (
        <div className="card border-l-4 border-rose-400 bg-rose-50 text-sm text-rose-900">
          {error}
        </div>
      )}

      <div className="rounded-xl overflow-hidden ring-1 ring-slate-200" style={{ height: "70vh" }}>
        <MapContainer center={DEFAULT_CENTER} zoom={11} scrollWheelZoom>
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          {incidents.map((inc) => (
            <Marker key={`i:${inc.id}`} position={[inc.lat, inc.lng]} icon={incidentIcon(inc.status)}>
              <Popup>
                <div className="text-sm space-y-1">
                  <div className="flex items-center gap-2">
                    <StatusPill status={inc.status} />
                    <span className="text-slate-500 text-xs">
                      {new Date(inc.created_at).toLocaleTimeString()}
                    </span>
                  </div>
                  <div className="text-slate-700">
                    {inc.lat.toFixed(4)}, {inc.lng.toFixed(4)}
                  </div>
                  {inc.eta_minutes != null && (
                    <div className="text-slate-500 text-xs">ETA {inc.eta_minutes} min</div>
                  )}
                  <Link
                    to={`/incidents?focus=${inc.id}`}
                    className="text-brand-700 text-xs font-medium"
                  >
                    Open in Incidents →
                  </Link>
                </div>
              </Popup>
            </Marker>
          ))}
          {Object.values(providers)
            .filter((p) => p.lat !== 0 || p.lng !== 0)
            .map((p) => {
              const state: "available" | "on_job" | "offline" =
                p.on_job ? "on_job" :
                p.is_available ? "available" : "offline";
              return (
                <Marker
                  key={`p:${p.id}`}
                  position={[p.lat, p.lng]}
                  icon={providerIcon(state)}
                >
                  <Popup>
                    <div className="text-sm space-y-0.5">
                      <div className="font-semibold text-slate-900">{p.name}</div>
                      <div className="text-slate-600">{p.service_type}</div>
                      <div className="text-xs text-slate-500">
                        {state.replace("_", " ")} · last ping{" "}
                        {new Date(p.last_seen).toLocaleTimeString()}
                      </div>
                    </div>
                  </Popup>
                </Marker>
              );
            })}
          <FitOnce points={points} />
        </MapContainer>
      </div>

      <Legend />
      {loading && (
        <p className="text-xs text-slate-500">Loading initial data…</p>
      )}
    </div>
  );
}

function providerMarkerFromList(
  p: ProviderListItem,
  onJob: boolean
): ProviderMarker {
  return {
    id: p.id,
    name: p.name,
    service_type: p.service_type,
    is_available: p.is_available,
    on_job: onJob,
    // The /api/providers list endpoint doesn't return PostGIS coords today,
    // so initialize at (0,0) and let PROVIDER_LOCATION events fill them in.
    // Markers at (0,0) are filtered out before rendering.
    lat: 0,
    lng: 0,
    last_seen: p.last_ping || new Date(0).toISOString(),
  };
}

function ConnectionDot({
  status, eventTick,
}: {
  status: string;
  eventTick: number;
}) {
  const cls =
    status === "open"       ? "bg-emerald-500" :
    status === "connecting" ? "bg-amber-400 animate-pulse" :
    status === "error" || status === "closed" ? "bg-rose-500" :
                              "bg-slate-300";
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-slate-600">
      <span className={`inline-block h-2.5 w-2.5 rounded-full ${cls}`} />
      live · {eventTick} event{eventTick === 1 ? "" : "s"}
    </span>
  );
}

function Legend() {
  return (
    <div className="card text-xs flex flex-wrap gap-x-5 gap-y-2 items-center">
      <span className="font-semibold text-slate-700 mr-2">Legend:</span>
      {Object.entries(STATUS_COLOR).map(([k, v]) => (
        <span key={k} className="flex items-center gap-1.5">
          <span className="inline-block h-3 w-3 rounded-full ring-1 ring-white shadow" style={{ background: v }} />
          {k}
        </span>
      ))}
      <span className="mx-2 text-slate-300">|</span>
      <span className="flex items-center gap-1.5">
        <span className="inline-block h-3 w-3 bg-emerald-600 ring-1 ring-white shadow" /> provider available
      </span>
      <span className="flex items-center gap-1.5">
        <span className="inline-block h-3 w-3 bg-blue-600 ring-1 ring-white shadow" /> on job
      </span>
      <span className="flex items-center gap-1.5">
        <span className="inline-block h-3 w-3 bg-slate-400 ring-1 ring-white shadow" /> offline
      </span>
    </div>
  );
}
