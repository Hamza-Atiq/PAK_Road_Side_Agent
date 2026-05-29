// Visual step indicator for the incident lifecycle.

import type { IncidentStatus } from "@/types/api";

const STEPS: { key: IncidentStatus; label: string }[] = [
  { key: "REPORTED", label: "Reported" },
  { key: "ANALYZING", label: "Analyzing" },
  { key: "ASSIGNED", label: "Assigned" },
  { key: "EN_ROUTE", label: "En route" },
  { key: "ARRIVED", label: "Arrived" },
  { key: "COMPLETED", label: "Completed" },
];

function indexFor(status: IncidentStatus): number {
  const i = STEPS.findIndex((s) => s.key === status);
  return i === -1 ? 0 : i;
}

export function StatusStepper({ status }: { status: IncidentStatus }) {
  const current = indexFor(status);
  const isProblem =
    status === "NO_PROVIDER" ||
    status === "ESCALATED" ||
    status === "CLOSED";

  return (
    <div className="w-full">
      <ol className="grid grid-cols-3 sm:grid-cols-6 gap-2">
        {STEPS.map((step, idx) => {
          const done = idx < current;
          const active = idx === current && !isProblem;
          return (
            <li key={step.key} className="flex flex-col items-center text-center">
              <div
                className={[
                  "h-8 w-8 rounded-full grid place-items-center text-xs font-semibold",
                  done && "bg-brand-600 text-white",
                  active && "bg-brand-100 text-brand-700 ring-2 ring-brand-500",
                  !done && !active && "bg-slate-100 text-slate-400",
                ]
                  .filter(Boolean)
                  .join(" ")}
              >
                {done ? "✓" : idx + 1}
              </div>
              <span
                className={`mt-1 text-[11px] sm:text-xs ${
                  done || active ? "text-slate-800" : "text-slate-400"
                }`}
              >
                {step.label}
              </span>
            </li>
          );
        })}
      </ol>
      {isProblem && (
        <p className="mt-3 text-sm text-rose-600">
          Status: <span className="font-semibold">{status}</span> — admin has
          been notified.
        </p>
      )}
    </div>
  );
}
