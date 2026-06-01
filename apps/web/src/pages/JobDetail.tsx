import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { incidentsApi } from "@/lib/api";
import type { Incident } from "@roadside/api-client";
import type { IncidentStatus } from "@roadside/types";
import { StatusStepper } from "@/components/StatusStepper";
import { MapView } from "@/components/MapView";

export function JobDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [incident, setIncident] = useState<Incident | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [updating, setUpdating] = useState(false);

  useEffect(() => {
    if (!id) return;
    incidentsApi
      .getOne(id)
      .then(setIncident)
      .catch(() => setError("Could not load this job."));
  }, [id]);

  const update = async (newStatus: IncidentStatus) => {
    if (!id) return;
    setUpdating(true);
    try {
      const updated = await incidentsApi.updateStatus(id, newStatus);
      setIncident(updated);
      if (newStatus === "COMPLETED") navigate("/provider", { replace: true });
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "Could not update status.";
      setError(typeof msg === "string" ? msg : "Could not update status.");
    } finally {
      setUpdating(false);
    }
  };

  if (error) {
    return <div className="mx-auto max-w-2xl py-10 text-center text-slate-600">{error}</div>;
  }
  if (!incident) {
    return <div className="mx-auto max-w-2xl py-10 text-center text-slate-500">Loading…</div>;
  }

  const nextActions = nextActionsFor(incident.status);

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <StatusStepper status={incident.status} />

      <MapView
        center={{ lat: incident.lat, lng: incident.lng }}
        pins={[
          { id: "incident", lat: incident.lat, lng: incident.lng, color: "red", label: "Customer" },
        ]}
        height="320px"
      />

      <div className="rounded-2xl border border-slate-200 bg-white p-5">
        <h2 className="text-lg font-bold text-slate-900">Incident</h2>
        <dl className="mt-3 grid gap-2 text-sm">
          <Row k="Issue" v={incident.service_type ?? "—"} />
          {incident.diagnosis && <Row k="Diagnosis" v={incident.diagnosis} />}
          {incident.description && <Row k="Customer note" v={incident.description} />}
          {incident.address && <Row k="Address" v={incident.address} />}
          <Row k="Reported" v={new Date(incident.created_at).toLocaleString()} />
        </dl>
        {incident.image_url && (
          <img
            src={incident.image_url}
            alt="Incident photo"
            className="mt-4 max-h-72 w-full rounded-lg object-cover"
          />
        )}
      </div>

      {nextActions.length > 0 && (
        <div className="sticky bottom-4 space-y-2">
          {nextActions.map((a) => (
            <button
              key={a.status}
              onClick={() => update(a.status)}
              disabled={updating}
              className={`${a.className} w-full text-lg shadow-2xl`}
            >
              {updating ? "Updating…" : a.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-3 border-b border-slate-100 pb-1.5 last:border-0">
      <dt className="text-slate-500">{k}</dt>
      <dd className="max-w-[60%] text-right capitalize text-slate-900">{v}</dd>
    </div>
  );
}

function nextActionsFor(
  status: IncidentStatus,
): { status: IncidentStatus; label: string; className: string }[] {
  switch (status) {
    case "ASSIGNED":
      return [
        {
          status: "EN_ROUTE",
          label: "🚗 Start driving (On the way)",
          className: "btn-secondary",
        },
      ];
    case "EN_ROUTE":
      return [
        {
          status: "ARRIVED",
          label: "📍 I've arrived",
          className:
            "inline-flex items-center justify-center gap-2 rounded-xl bg-warning px-6 py-4 text-lg font-semibold text-white shadow-lg shadow-warning/30 hover:brightness-110",
        },
      ];
    case "ARRIVED":
      return [
        {
          status: "COMPLETED",
          label: "✓ Mark job complete",
          className: "btn-secondary",
        },
      ];
    default:
      return [];
  }
}
