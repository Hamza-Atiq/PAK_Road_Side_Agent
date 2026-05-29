import type { IncidentStatus } from "@/types/api";

const STYLES: Record<IncidentStatus, string> = {
  REPORTED:     "bg-slate-100 text-slate-700",
  ANALYZING:    "bg-sky-100 text-sky-800",
  ASSIGNED:     "bg-indigo-100 text-indigo-800",
  NO_PROVIDER:  "bg-rose-100 text-rose-800 ring-1 ring-rose-300",
  ESCALATED:    "bg-orange-100 text-orange-800 ring-1 ring-orange-300",
  EN_ROUTE:     "bg-amber-100 text-amber-800",
  ARRIVED:      "bg-violet-100 text-violet-800",
  COMPLETED:    "bg-emerald-100 text-emerald-800",
  CLOSED:       "bg-slate-100 text-slate-500",
};

export function StatusPill({ status }: { status: IncidentStatus | string }) {
  const cls = (STYLES as Record<string, string>)[status] || "bg-slate-100 text-slate-700";
  return (
    <span className={`inline-block text-[11px] font-medium px-2 py-0.5 rounded ${cls}`}>
      {status}
    </span>
  );
}
