import { FormEvent, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { incidentsApi } from "@/api/incidents";
import { adminApi } from "@/api/admin";
import { StatusPill } from "@/components/StatusPill";
import type { Incident, IncidentBrief, IncidentStatus } from "@/types/api";

const STATUS_FILTERS: (IncidentStatus | "ALL")[] = [
  "ALL",
  "REPORTED", "ANALYZING", "ASSIGNED",
  "NO_PROVIDER", "ESCALATED",
  "EN_ROUTE", "ARRIVED",
  "COMPLETED", "CLOSED",
];

const PAGE_SIZE = 25;

export function Incidents() {
  const [searchParams, setSearchParams] = useSearchParams();
  const focusId = searchParams.get("focus");
  const initialStatus = (searchParams.get("status") as IncidentStatus | null) || null;

  const [statusFilter, setStatusFilter] = useState<IncidentStatus | "ALL">(
    initialStatus ?? "ALL"
  );
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<IncidentBrief[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Incident | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await incidentsApi.list({
        status: statusFilter === "ALL" ? null : statusFilter,
        limit: PAGE_SIZE,
        offset,
      });
      setItems(resp.items);
      setTotal(resp.total);
      setError(null);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Could not load incidents.");
    } finally {
      setLoading(false);
    }
  }, [statusFilter, offset]);

  useEffect(() => { void fetch(); }, [fetch]);

  // Reset offset when filter changes, and persist filter to URL
  useEffect(() => {
    setOffset(0);
    const next = new URLSearchParams(searchParams);
    if (statusFilter === "ALL") next.delete("status"); else next.set("status", statusFilter);
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  // Auto-open the detail modal if `?focus=<id>` is present (deep link from
  // the Live Map). Only run once on first load with that id.
  useEffect(() => {
    if (!focusId) return;
    void openDetail(focusId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusId]);

  async function openDetail(id: string) {
    try {
      const inc = await incidentsApi.getOne(id);
      setSelected(inc);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Could not load incident.");
    }
  }

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <div className="space-y-4">
      <header className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Incidents</h1>
          <p className="text-sm text-slate-500">
            {total} total · page {currentPage} of {pageCount}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="label mb-0">Filter</label>
          <select
            className="input max-w-[180px]"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as IncidentStatus | "ALL")}
          >
            {STATUS_FILTERS.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <button onClick={() => void fetch()} className="btn-secondary text-sm">Refresh</button>
        </div>
      </header>

      {error && (
        <div className="card border-l-4 border-rose-400 bg-rose-50 text-sm text-rose-900">{error}</div>
      )}

      <div className="card p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-slate-50">
              <tr>
                <th className="table-th">ID</th>
                <th className="table-th">Status</th>
                <th className="table-th">Created</th>
                <th className="table-th">Location</th>
                <th className="table-th">Provider</th>
                <th className="table-th">ETA</th>
                <th className="table-th"></th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 && !loading && (
                <tr>
                  <td colSpan={7} className="px-3 py-10 text-center text-slate-500 text-sm">
                    No incidents match this filter.
                  </td>
                </tr>
              )}
              {items.map((inc) => (
                <tr key={inc.id} className="hover:bg-slate-50 cursor-pointer" onClick={() => void openDetail(inc.id)}>
                  <td className="table-td font-mono text-xs">{inc.id.slice(0, 8)}</td>
                  <td className="table-td"><StatusPill status={inc.status} /></td>
                  <td className="table-td text-xs text-slate-500">
                    {new Date(inc.created_at).toLocaleString()}
                  </td>
                  <td className="table-td text-xs">
                    {inc.lat.toFixed(4)}, {inc.lng.toFixed(4)}
                  </td>
                  <td className="table-td text-xs font-mono">
                    {inc.provider_id ? inc.provider_id.slice(0, 8) : <span className="text-slate-400">—</span>}
                  </td>
                  <td className="table-td text-xs">
                    {inc.eta_minutes != null ? `${inc.eta_minutes}m` : "—"}
                  </td>
                  <td className="table-td text-xs">
                    <span className="text-brand-700 font-medium">Details →</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="flex items-center justify-between px-3 py-3 border-t border-slate-100 text-sm text-slate-600">
          <span>
            Showing {items.length === 0 ? 0 : offset + 1}–{Math.min(offset + items.length, total)} of {total}
          </span>
          <div className="flex items-center gap-2">
            <button
              className="btn-secondary text-sm py-1.5 px-3"
              disabled={offset === 0 || loading}
              onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
            >
              ← Prev
            </button>
            <button
              className="btn-secondary text-sm py-1.5 px-3"
              disabled={offset + PAGE_SIZE >= total || loading}
              onClick={() => setOffset((o) => o + PAGE_SIZE)}
            >
              Next →
            </button>
          </div>
        </div>
      </div>

      {selected && (
        <IncidentDetailModal
          incident={selected}
          onClose={() => {
            setSelected(null);
            // Strip ?focus= so closing-and-reopening another row doesn't re-fire
            if (focusId) {
              const next = new URLSearchParams(searchParams);
              next.delete("focus");
              setSearchParams(next, { replace: true });
            }
          }}
          onChanged={() => { void fetch(); }}
        />
      )}
    </div>
  );
}

function IncidentDetailModal({
  incident, onClose, onChanged,
}: {
  incident: Incident;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [reassignBusy, setReassignBusy] = useState(false);
  const [specificProviderId, setSpecificProviderId] = useState("");
  const [reassignResult, setReassignResult] = useState<string | null>(null);
  const [reassignError, setReassignError] = useState<string | null>(null);

  const [closeBusy, setCloseBusy] = useState(false);
  const [closeReason, setCloseReason] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  async function doReassign(e: FormEvent) {
    e.preventDefault();
    setReassignBusy(true);
    setReassignResult(null);
    setReassignError(null);
    try {
      const resp = await adminApi.reassign(incident.id, {
        new_provider_id: specificProviderId.trim() || null,
        reason: "admin manual reassign",
      });
      setReassignResult(
        resp.new_provider_name
          ? `Reassigned to ${resp.new_provider_name}. ${resp.notes}`
          : `Status: ${resp.status}. ${resp.notes}`
      );
      onChanged();
    } catch (err: any) {
      setReassignError(err?.response?.data?.detail || "Reassign failed.");
    } finally {
      setReassignBusy(false);
    }
  }

  async function doClose() {
    if (!confirm("Force-close this incident? This is final.")) return;
    setCloseBusy(true);
    setActionError(null);
    try {
      await incidentsApi.close(incident.id, closeReason || "closed by admin");
      onChanged();
      onClose();
    } catch (err: any) {
      setActionError(err?.response?.data?.detail || "Close failed.");
      setCloseBusy(false);
    }
  }

  const reassignable = !["COMPLETED", "CLOSED"].includes(incident.status);

  return (
    <div
      className="fixed inset-0 z-40 bg-slate-900/50 flex items-start justify-center p-4 overflow-y-auto"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl bg-white rounded-xl shadow-xl my-8"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between gap-3 px-5 py-4 border-b border-slate-100">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold text-slate-900">
                Incident {incident.id.slice(0, 8)}
              </h2>
              <StatusPill status={incident.status} />
              {incident.guardrail_flagged && (
                <span className="text-[10px] font-semibold uppercase tracking-wide bg-rose-100 text-rose-800 px-1.5 py-0.5 rounded">
                  Guardrail
                </span>
              )}
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              Created {new Date(incident.created_at).toLocaleString()} ·
              Updated {new Date(incident.updated_at).toLocaleString()}
            </p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700 text-2xl leading-none px-2">
            ×
          </button>
        </header>

        <div className="px-5 py-4 space-y-4 text-sm">
          <DetailRow label="Customer ID" value={incident.customer_id} mono />
          <DetailRow
            label="Provider ID"
            value={incident.provider_id || "(none)"}
            mono={!!incident.provider_id}
          />
          <DetailRow
            label="Location"
            value={`${incident.lat.toFixed(5)}, ${incident.lng.toFixed(5)}`}
          />
          {incident.address && <DetailRow label="Address" value={incident.address} />}
          {incident.eta_minutes != null && (
            <DetailRow label="ETA" value={`${incident.eta_minutes} min`} />
          )}
          {incident.description && (
            <DetailRow label="Description" value={incident.description} />
          )}
          {incident.ai_diagnosis && (
            <div>
              <div className="label">AI diagnosis</div>
              <div className="text-xs bg-slate-50 ring-1 ring-slate-200 rounded p-2 space-y-1">
                <div><b>Issue:</b> {incident.ai_diagnosis.issue_type}</div>
                <div><b>Service needed:</b> {incident.ai_diagnosis.service_needed}</div>
                <div><b>Severity:</b> {incident.ai_diagnosis.severity}</div>
                <div><b>Confidence:</b> {(incident.ai_diagnosis.confidence * 100).toFixed(0)}%</div>
                {incident.ai_diagnosis.details && (
                  <div className="text-slate-600">{incident.ai_diagnosis.details}</div>
                )}
              </div>
            </div>
          )}
          {incident.image_url && (
            <div>
              <div className="label">Photo</div>
              <a href={incident.image_url} target="_blank" rel="noreferrer">
                <img
                  src={incident.image_url}
                  alt="incident"
                  className="rounded ring-1 ring-slate-200 max-h-48"
                />
              </a>
            </div>
          )}
        </div>

        {reassignable && (
          <div className="px-5 py-4 border-t border-slate-100 space-y-3">
            <h3 className="font-semibold text-slate-900 text-sm">Reassign</h3>
            <form className="flex flex-col sm:flex-row gap-2" onSubmit={doReassign}>
              <input
                className="input flex-1"
                placeholder="Specific provider UUID (optional — leave blank to auto-pick)"
                value={specificProviderId}
                onChange={(e) => setSpecificProviderId(e.target.value)}
              />
              <button className="btn-primary text-sm whitespace-nowrap" disabled={reassignBusy}>
                {reassignBusy ? "Reassigning…" : "Reassign"}
              </button>
            </form>
            {reassignResult && <p className="text-xs text-emerald-700">{reassignResult}</p>}
            {reassignError && <p className="text-xs text-rose-700">{reassignError}</p>}
          </div>
        )}

        {incident.status !== "CLOSED" && (
          <div className="px-5 py-4 border-t border-slate-100 space-y-2">
            <h3 className="font-semibold text-slate-900 text-sm">Force-close</h3>
            <div className="flex gap-2">
              <input
                className="input flex-1 text-sm"
                placeholder="Reason (optional)"
                value={closeReason}
                onChange={(e) => setCloseReason(e.target.value)}
              />
              <button onClick={doClose} className="btn-danger text-sm whitespace-nowrap" disabled={closeBusy}>
                {closeBusy ? "Closing…" : "Close incident"}
              </button>
            </div>
            {actionError && <p className="text-xs text-rose-700">{actionError}</p>}
          </div>
        )}
      </div>
    </div>
  );
}

function DetailRow({
  label, value, mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="grid grid-cols-3 gap-2 items-baseline">
      <div className="text-xs uppercase tracking-wider text-slate-500">{label}</div>
      <div className={`col-span-2 text-slate-800 ${mono ? "font-mono text-xs break-all" : ""}`}>
        {value}
      </div>
    </div>
  );
}

