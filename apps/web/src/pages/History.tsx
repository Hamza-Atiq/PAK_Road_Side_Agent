import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { incidentsApi } from "@/lib/api";
import type { Incident } from "@roadside/api-client";

const STATUS_COLOR: Record<string, string> = {
  COMPLETED: "bg-success/10 text-success",
  CLOSED: "bg-slate-100 text-slate-600",
  EN_ROUTE: "bg-warning/10 text-warning",
  ASSIGNED: "bg-brand-customer/10 text-brand-customer-dark",
  ANALYZING: "bg-amber-100 text-amber-800",
  REPORTED: "bg-amber-100 text-amber-800",
  ARRIVED: "bg-brand-provider/10 text-brand-provider-dark",
  NO_PROVIDER: "bg-red-100 text-red-700",
  ESCALATED: "bg-red-100 text-red-700",
};

interface Props {
  role: "customer" | "provider";
}

export function History({ role }: Props) {
  const [items, setItems] = useState<Incident[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load =
      role === "provider"
        ? incidentsApi.listAssigned(true)
        : incidentsApi.listMine(50, 0);
    load
      .then((r) => setItems(r.items))
      .catch(() => setError("Could not load history."));
  }, [role]);

  if (error) {
    return <div className="mx-auto max-w-2xl py-10 text-center text-slate-600">{error}</div>;
  }
  if (!items) {
    return <div className="mx-auto max-w-2xl py-10 text-center text-slate-500">Loading…</div>;
  }
  if (items.length === 0) {
    return (
      <div className="mx-auto max-w-md py-16 text-center">
        <div className="text-5xl">📭</div>
        <h2 className="mt-4 text-xl font-bold text-slate-900">No history yet</h2>
        <p className="mt-2 text-sm text-slate-600">
          {role === "customer"
            ? "Your past incidents will appear here."
            : "Your past jobs will appear here."}
        </p>
      </div>
    );
  }

  const detailHref = (id: string) =>
    role === "provider" ? `/provider/jobs/${id}` : `/customer/incidents/${id}`;

  return (
    <div className="mx-auto max-w-3xl space-y-3">
      <h1 className="text-2xl font-bold text-slate-900">History</h1>
      <ul className="space-y-2">
        {items.map((i) => (
          <li key={i.id}>
            <Link
              to={detailHref(i.id)}
              className="flex items-center gap-4 rounded-2xl border border-slate-200 bg-white p-4 transition hover:border-slate-300 hover:shadow-sm"
            >
              <div className="text-2xl" aria-hidden>
                {iconFor(i.service_type ?? "other")}
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-semibold capitalize text-slate-900">
                    {i.service_type ?? "incident"}
                  </span>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${STATUS_COLOR[i.status] ?? "bg-slate-100 text-slate-600"}`}
                  >
                    {i.status}
                  </span>
                </div>
                <div className="text-xs text-slate-500">
                  {new Date(i.created_at).toLocaleString()}
                </div>
              </div>
              <span aria-hidden className="text-slate-400">
                →
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

function iconFor(t: string): string {
  switch (t) {
    case "tow":
      return "🚛";
    case "battery":
      return "🔋";
    case "tire":
      return "🛞";
    case "fuel":
      return "⛽";
    case "lockout":
      return "🔑";
    default:
      return "🆘";
  }
}
