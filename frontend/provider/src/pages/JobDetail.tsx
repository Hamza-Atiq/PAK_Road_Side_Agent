import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { incidentsApi } from "@/api/incidents";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useGeolocation } from "@/hooks/useGeolocation";
import { MapView } from "@/components/MapView";
import type { Incident, IncidentStatus } from "@/types/api";

const SEVERITY_COLOR: Record<string, string> = {
  low: "bg-emerald-100 text-emerald-800",
  medium: "bg-amber-100 text-amber-800",
  high: "bg-orange-100 text-orange-800",
  critical: "bg-rose-100 text-rose-800",
  unknown: "bg-slate-100 text-slate-700",
};

// Map current status → next allowed transition for the provider.
const NEXT_ACTION: Partial<
  Record<IncidentStatus, { label: string; next: IncidentStatus }>
> = {
  ASSIGNED: { label: "I'm on the way", next: "EN_ROUTE" },
  EN_ROUTE: { label: "I've arrived", next: "ARRIVED" },
  ARRIVED: { label: "Job complete", next: "COMPLETED" },
};

export function JobDetail() {
  const { id } = useParams<{ id: string }>();
  const [incident, setIncident] = useState<Incident | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [transitioning, setTransitioning] = useState(false);

  // Provider's own GPS — for the map and the dashed line to the customer
  const geo = useGeolocation();

  const refetch = useCallback(async () => {
    if (!id) return;
    try {
      const data = await incidentsApi.getOne(id);
      setIncident(data);
      setError(null);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Could not load job.");
    }
  }, [id]);

  useEffect(() => {
    refetch();
    geo.request();
    const t = setInterval(refetch, 15_000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refetch]);

  useWebSocket({
    path: id ? `/ws/incidents/${id}` : "",
    enabled: !!id,
    onEvent: () => void refetch(),
  });

  async function advance(next: IncidentStatus) {
    if (!id) return;
    setTransitioning(true);
    try {
      const updated = await incidentsApi.updateStatus(id, next);
      setIncident(updated);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Could not update status.");
    } finally {
      setTransitioning(false);
    }
  }

  if (error && !incident) {
    return (
      <div className="card">
        <p className="text-sm text-rose-600">{error}</p>
        <Link to="/dashboard" className="btn-secondary mt-3 inline-flex">
          ← Back to dashboard
        </Link>
      </div>
    );
  }
  if (!incident) {
    return <div className="card animate-pulse"><div className="h-5 w-40 bg-slate-200 rounded" /></div>;
  }

  const ai = incident.ai_diagnosis;
  const action = NEXT_ACTION[incident.status];
  const terminal =
    incident.status === "COMPLETED" ||
    incident.status === "CLOSED" ||
    incident.status === "ESCALATED";

  return (
    <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
      <div className="lg:col-span-3 space-y-4">
        <div className="card flex items-center justify-between gap-3">
          <div>
            <h1 className="text-lg font-semibold text-slate-900">Active job</h1>
            <p className="text-xs text-slate-500 mt-0.5">
              {incident.address || "no address provided"} · created{" "}
              {new Date(incident.created_at).toLocaleString()}
            </p>
          </div>
          <span className="text-xs font-semibold px-2 py-1 rounded bg-indigo-100 text-indigo-800">
            {incident.status}
          </span>
        </div>

        <div className="card p-0 overflow-hidden">
          <MapView
            customerLat={incident.lat}
            customerLng={incident.lng}
            providerLat={geo.position?.lat}
            providerLng={geo.position?.lng}
            height="360px"
          />
          <div className="px-4 py-3 border-t border-slate-200 text-xs text-slate-600 flex items-center justify-between gap-3">
            <span>
              Customer:{" "}
              <code className="text-slate-800">
                {incident.lat.toFixed(5)}, {incident.lng.toFixed(5)}
              </code>
            </span>
            {geo.position ? (
              <span>
                You:{" "}
                <code className="text-slate-800">
                  {geo.position.lat.toFixed(5)}, {geo.position.lng.toFixed(5)}
                </code>
              </span>
            ) : (
              <button onClick={geo.request} className="btn-secondary text-xs">
                Locate me
              </button>
            )}
          </div>
        </div>

        {incident.description && (
          <div className="card">
            <h2 className="text-sm font-semibold text-slate-900">Customer note</h2>
            <p className="mt-2 text-sm text-slate-700 whitespace-pre-wrap">
              {incident.description}
            </p>
          </div>
        )}

        {incident.image_url && (
          <div className="card">
            <h2 className="text-sm font-semibold text-slate-900">Photo</h2>
            <img
              src={incident.image_url}
              alt="incident"
              className="mt-2 rounded-lg max-h-72 mx-auto"
            />
          </div>
        )}

        {incident.voice_url && (
          <div className="card">
            <h2 className="text-sm font-semibold text-slate-900">Voice note</h2>
            <audio controls className="mt-2 w-full" src={incident.voice_url} />
          </div>
        )}
      </div>

      <div className="lg:col-span-2 space-y-4">
        {ai && (
          <div className="card">
            <h2 className="text-sm font-semibold text-slate-900">AI diagnosis</h2>
            <div className="mt-3 space-y-2 text-sm">
              <Row label="Issue" value={ai.issue_type} />
              <Row
                label="Severity"
                valueNode={
                  <span
                    className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                      SEVERITY_COLOR[ai.severity] || SEVERITY_COLOR.unknown
                    }`}
                  >
                    {ai.severity}
                  </span>
                }
              />
              <Row label="Service" value={ai.service_needed} />
              <Row label="Confidence" value={`${Math.round(ai.confidence * 100)}%`} />
              {ai.details && (
                <p className="text-xs text-slate-600 mt-2">{ai.details}</p>
              )}
            </div>
          </div>
        )}

        <div className="card">
          <h2 className="text-sm font-semibold text-slate-900">Update status</h2>
          {action && !terminal ? (
            <button
              onClick={() => advance(action.next)}
              disabled={transitioning}
              className="btn-primary w-full mt-3"
            >
              {transitioning ? "Updating…" : action.label}
            </button>
          ) : (
            <p className="mt-3 text-sm text-slate-600">
              {terminal
                ? "This job is closed."
                : `Status: ${incident.status} — no action available.`}
            </p>
          )}
          {error && <p className="text-xs text-rose-600 mt-2">{error}</p>}
        </div>

        <Link to="/dashboard" className="btn-secondary w-full text-center">
          ← Back to dashboard
        </Link>
      </div>
    </div>
  );
}

function Row({
  label, value, valueNode,
}: { label: string; value?: string; valueNode?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-slate-500">{label}</span>
      {valueNode ?? <span className="font-medium text-slate-900">{value}</span>}
    </div>
  );
}
