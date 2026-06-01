import type { IncidentStatus } from "@roadside/types";

const ORDER: IncidentStatus[] = [
  "REPORTED",
  "ANALYZING",
  "ASSIGNED",
  "EN_ROUTE",
  "ARRIVED",
  "COMPLETED",
];

const LABEL: Record<IncidentStatus, string> = {
  REPORTED: "Received",
  ANALYZING: "Analyzing",
  ASSIGNED: "Provider found",
  EN_ROUTE: "On the way",
  ARRIVED: "Arrived",
  COMPLETED: "Done",
  CLOSED: "Closed",
  NO_PROVIDER: "Searching",
  ESCALATED: "Escalated",
};

export function StatusStepper({ status }: { status: IncidentStatus }) {
  const isTerminal = status === "CLOSED" || status === "NO_PROVIDER" || status === "ESCALATED";
  const currentIdx = ORDER.indexOf(status);

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Current status
          </div>
          <div className="text-lg font-bold text-slate-900">{LABEL[status] ?? status}</div>
        </div>
        {isTerminal && (
          <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-800">
            {status}
          </span>
        )}
      </div>

      <ol className="grid grid-cols-6 gap-1">
        {ORDER.map((s, i) => {
          const done = currentIdx >= i;
          const active = currentIdx === i;
          return (
            <li key={s} className="flex flex-col items-center gap-1.5">
              <span
                className={`h-2 w-full rounded-full transition ${
                  done ? "bg-brand-customer" : "bg-slate-200"
                } ${active ? "ring-2 ring-brand-customer/30" : ""}`}
              />
              <span
                className={`text-[10px] font-medium leading-tight text-center ${
                  active ? "text-slate-900" : done ? "text-slate-600" : "text-slate-400"
                }`}
              >
                {LABEL[s]}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
