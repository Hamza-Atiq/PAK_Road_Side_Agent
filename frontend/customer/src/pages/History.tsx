import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { incidentsApi } from "@/api/incidents";
import type { IncidentBrief, IncidentStatus } from "@/types/api";

const STATUS_STYLE: Record<IncidentStatus, string> = {
  REPORTED: "bg-slate-100 text-slate-700",
  ANALYZING: "bg-sky-100 text-sky-800",
  ASSIGNED: "bg-indigo-100 text-indigo-800",
  EN_ROUTE: "bg-amber-100 text-amber-800",
  ARRIVED: "bg-violet-100 text-violet-800",
  COMPLETED: "bg-emerald-100 text-emerald-800",
  CLOSED: "bg-slate-100 text-slate-500",
  NO_PROVIDER: "bg-rose-100 text-rose-800",
  ESCALATED: "bg-rose-200 text-rose-900",
};

export function History() {
  const [items, setItems] = useState<IncidentBrief[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const data = await incidentsApi.listMine(50, 0);
        setItems(data.items);
      } catch (err: any) {
        setError(err?.response?.data?.detail || "Could not load history.");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return (
      <div className="card animate-pulse">
        <div className="h-5 w-40 bg-slate-200 rounded" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="card">
        <p className="text-sm text-rose-600">{error}</p>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="card text-center">
        <h1 className="text-lg font-semibold text-slate-900">No incidents yet</h1>
        <p className="text-sm text-slate-600 mt-1">
          When you report a breakdown, it'll show up here.
        </p>
        <Link to="/report" className="btn-primary mt-4 inline-flex">
          Report an incident
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <h1 className="text-lg font-semibold text-slate-900 px-1">Your incidents</h1>
      {items.map((i) => (
        <Link
          key={i.id}
          to={`/incidents/${i.id}`}
          className="card flex items-center justify-between gap-4 hover:ring-brand-300 hover:shadow-md transition"
        >
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span
                className={`text-[11px] font-medium px-2 py-0.5 rounded ${
                  STATUS_STYLE[i.status] || "bg-slate-100 text-slate-700"
                }`}
              >
                {i.status}
              </span>
              <span className="text-xs text-slate-500">
                {new Date(i.created_at).toLocaleString()}
              </span>
            </div>
            <p className="mt-1 text-sm text-slate-700 truncate">
              {i.lat.toFixed(4)}, {i.lng.toFixed(4)}
              {i.eta_minutes != null && (
                <span className="ml-2 text-slate-500">
                  · ETA {i.eta_minutes} min
                </span>
              )}
            </p>
          </div>
          <span className="text-slate-400 text-xl">→</span>
        </Link>
      ))}
    </div>
  );
}
