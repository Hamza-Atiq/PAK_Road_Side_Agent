import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { connectWS, type Incident } from "@roadside/api-client";
import { incidentsApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import { StatusStepper } from "@/components/StatusStepper";
import { MapView } from "@/components/MapView";

export function IncidentStatus() {
  const { id } = useParams<{ id: string }>();
  const accessToken = useAuthStore((s) => s.accessToken);
  const [incident, setIncident] = useState<Incident | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Initial fetch
  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    incidentsApi
      .getOne(id)
      .then((i) => !cancelled && setIncident(i))
      .catch(() => !cancelled && setError("Could not load this incident."));
    return () => {
      cancelled = true;
    };
  }, [id]);

  // WebSocket live updates
  useEffect(() => {
    if (!id || !accessToken) return;
    const baseWS = (import.meta.env.VITE_WS_BASE_URL || "") || "/";
    const url = `${baseWS}ws/incidents/${id}`.replace(/^http/, "ws");
    const absolute = url.startsWith("ws") ? url : `${window.location.origin.replace(/^http/, "ws")}${url}`;

    const handle = connectWS({
      url: absolute,
      token: accessToken,
      onMessage: (msg) => {
        const m = msg as { type?: string; incident?: Incident };
        if (m?.incident) setIncident(m.incident);
      },
    });
    return () => handle.close();
  }, [id, accessToken]);

  const shareLink = id
    ? `${window.location.origin}/share/${id}`
    : "";

  const copyShare = async () => {
    if (!shareLink) return;
    try {
      await navigator.clipboard.writeText(shareLink);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* noop */
    }
  };

  if (error) {
    return (
      <div className="mx-auto max-w-md py-10 text-center text-slate-600">
        <p>{error}</p>
      </div>
    );
  }

  if (!incident) {
    return (
      <div className="mx-auto max-w-md py-10 text-center text-slate-500">Loading…</div>
    );
  }

  type Pin = { id: string; lat: number; lng: number; color: "red" | "orange" | "blue" | "green"; label: string };
  const pins: Pin[] = [
    { id: "incident", lat: incident.lat, lng: incident.lng, color: "red", label: "You" },
  ];
  if (incident.provider?.last_lat && incident.provider?.last_lng) {
    pins.push({
      id: "provider",
      lat: incident.provider.last_lat,
      lng: incident.provider.last_lng,
      color: "orange",
      label: incident.provider.name ?? "Provider",
    });
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <StatusStepper status={incident.status} />

      <MapView center={{ lat: incident.lat, lng: incident.lng }} pins={pins} height="320px" />

      {incident.provider ? (
        <ProviderCard incident={incident} />
      ) : (
        <div className="rounded-2xl border border-slate-200 bg-white p-5 text-center">
          <div className="text-3xl">🛰️</div>
          <h3 className="mt-2 text-lg font-semibold text-slate-900">Finding the closest help</h3>
          <p className="mt-1 text-sm text-slate-600">
            Our AI is analyzing your report and matching the best provider near you. Usually
            under 30 seconds.
          </p>
        </div>
      )}

      <div className="rounded-2xl border border-slate-200 bg-white p-5">
        <h3 className="text-sm font-semibold text-slate-900">Share with family</h3>
        <p className="mt-1 text-xs text-slate-500">
          Anyone with this link can see your live progress (read-only).
        </p>
        <div className="mt-3 flex gap-2">
          <input
            readOnly
            value={shareLink}
            className="flex-1 truncate rounded-lg border border-slate-300 bg-slate-50 px-3 py-2 text-xs text-slate-700"
          />
          <button
            onClick={copyShare}
            className="rounded-lg bg-brand-customer px-4 py-2 text-sm font-semibold text-white hover:bg-brand-customer-dark"
          >
            {copied ? "Copied!" : "Copy"}
          </button>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-5">
        <h3 className="text-sm font-semibold text-slate-900">Incident details</h3>
        <dl className="mt-3 grid gap-2 text-sm">
          <Row k="Reported at" v={new Date(incident.created_at).toLocaleString()} />
          {incident.service_type && <Row k="Issue" v={incident.service_type} />}
          {incident.diagnosis && <Row k="Diagnosis" v={incident.diagnosis} />}
          {incident.description && <Row k="Your note" v={incident.description} />}
          {incident.address && <Row k="Address" v={incident.address} />}
        </dl>
      </div>
    </div>
  );
}

function ProviderCard({ incident }: { incident: Incident }) {
  const p = incident.provider!;
  const showCall = !!p.phone;
  return (
    <div className="flex items-center gap-4 rounded-2xl border border-slate-200 bg-white p-5">
      <div className="grid h-14 w-14 place-items-center rounded-full bg-brand-provider/10 text-2xl">
        🔧
      </div>
      <div className="flex-1">
        <div className="text-lg font-bold text-slate-900">{p.name ?? "Verified provider"}</div>
        <div className="text-xs text-slate-500">
          {p.vehicle_info ?? "On the way"}
          {p.rating !== null && p.rating !== undefined && (
            <span className="ml-2 inline-flex items-center gap-0.5">
              ★ {p.rating.toFixed(1)}
            </span>
          )}
        </div>
      </div>
      {showCall && (
        <a
          href={`tel:${p.phone}`}
          className="rounded-xl bg-brand-customer px-4 py-2 text-sm font-semibold text-white shadow-md hover:bg-brand-customer-dark"
        >
          Call
        </a>
      )}
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-3 border-b border-slate-100 pb-1.5 last:border-0">
      <dt className="text-slate-500">{k}</dt>
      <dd className="max-w-[60%] text-right text-slate-900">{v}</dd>
    </div>
  );
}
