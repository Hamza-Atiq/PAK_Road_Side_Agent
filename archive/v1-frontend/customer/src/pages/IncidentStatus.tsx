import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { incidentsApi } from "@/api/incidents";
import { useWebSocket } from "@/hooks/useWebSocket";
import { MapView } from "@/components/MapView";
import { StatusStepper } from "@/components/StatusStepper";
import type { Incident } from "@/types/api";

const SEVERITY_COLOR: Record<string, string> = {
  low: "bg-emerald-100 text-emerald-800",
  medium: "bg-amber-100 text-amber-800",
  high: "bg-orange-100 text-orange-800",
  critical: "bg-rose-100 text-rose-800",
  unknown: "bg-slate-100 text-slate-700",
};

export function IncidentStatus() {
  const { id } = useParams<{ id: string }>();
  const [incident, setIncident] = useState<Incident | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [closingNow, setClosingNow] = useState(false);

  const refetch = useCallback(async () => {
    if (!id) return;
    try {
      const data = await incidentsApi.getOne(id);
      setIncident(data);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not load incident.");
    }
  }, [id]);

  useEffect(() => {
    refetch();
    const t = setInterval(refetch, 15_000); // belt-and-braces fallback
    return () => clearInterval(t);
  }, [refetch]);

  const { status: wsStatus } = useWebSocket({
    path: id ? `/ws/incidents/${id}` : "",
    enabled: !!id,
    onEvent: () => {
      // Any push event = something changed; refetch full record once.
      void refetch();
    },
  });

  if (error) {
    return (
      <div className="card">
        <h1 className="text-lg font-semibold text-rose-700">
          Couldn't open this incident
        </h1>
        <p className="mt-1 text-sm text-slate-600">{error}</p>
        <Link to="/report" className="btn-primary mt-4 inline-flex">
          Report a new incident
        </Link>
      </div>
    );
  }

  if (!incident) {
    return (
      <div className="card animate-pulse">
        <div className="h-5 w-40 bg-slate-200 rounded" />
        <div className="mt-3 h-4 w-60 bg-slate-200 rounded" />
      </div>
    );
  }

  const ai = incident.ai_diagnosis;
  const isTerminal =
    incident.status === "COMPLETED" ||
    incident.status === "CLOSED" ||
    incident.status === "ESCALATED";

  async function onClose() {
    if (!id) return;
    setClosingNow(true);
    try {
      const updated = await incidentsApi.close(id, "customer closed");
      setIncident(updated);
    } finally {
      setClosingNow(false);
    }
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
      <div className="lg:col-span-3 space-y-4">
        <div className="card">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h1 className="text-lg font-semibold text-slate-900">
                Incident status
              </h1>
              <p className="text-xs text-slate-500 mt-0.5">
                Live updates: {wsStatus}
              </p>
            </div>
            <span className="text-xs text-slate-500">
              {new Date(incident.created_at).toLocaleString()}
            </span>
          </div>
          <div className="mt-4">
            <StatusStepper status={incident.status} />
          </div>
        </div>

        <div className="card p-0 overflow-hidden">
          <MapView lat={incident.lat} lng={incident.lng} height="340px" />
        </div>
      </div>

      <div className="lg:col-span-2 space-y-4">
        {ai && (
          <div className="card">
            <h2 className="text-sm font-semibold text-slate-900">
              AI diagnosis
            </h2>
            <div className="mt-3 space-y-2">
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
              <Row
                label="Confidence"
                value={`${Math.round(ai.confidence * 100)}%`}
              />
              {ai.details && (
                <p className="text-xs text-slate-600 mt-2">{ai.details}</p>
              )}
            </div>
          </div>
        )}

        {incident.provider_id ? (
          <div className="card">
            <h2 className="text-sm font-semibold text-slate-900">Your provider</h2>
            <div className="mt-3 space-y-2">
              <Row label="ETA" value={
                incident.eta_minutes != null
                  ? `${incident.eta_minutes} min`
                  : "—"
              } />
              <Row label="Status" value={incident.status} />
            </div>
          </div>
        ) : (
          <div className="card">
            <h2 className="text-sm font-semibold text-slate-900">
              Finding help
            </h2>
            <p className="mt-2 text-sm text-slate-600">
              We're locating the nearest available provider.
            </p>
          </div>
        )}

        {!isTerminal && (
          <button
            onClick={onClose}
            disabled={closingNow}
            className="btn-secondary w-full"
          >
            {closingNow ? "Closing…" : "Cancel / close incident"}
          </button>
        )}
      </div>
    </div>
  );
}

function Row({
  label,
  value,
  valueNode,
}: {
  label: string;
  value?: string;
  valueNode?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-slate-500">{label}</span>
      {valueNode ?? <span className="font-medium text-slate-900">{value}</span>}
    </div>
  );
}
