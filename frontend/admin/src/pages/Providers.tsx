import { FormEvent, useCallback, useEffect, useState } from "react";
import { providersApi } from "@/api/providers";
import { adminApi } from "@/api/admin";
import type { ProviderListItem } from "@/types/api";

type ApprovalFilter = "ALL" | "APPROVED" | "PENDING";
type AvailFilter = "ALL" | "AVAILABLE" | "OFFLINE";

export function Providers() {
  const [items, setItems] = useState<ProviderListItem[]>([]);
  const [approval, setApproval] = useState<ApprovalFilter>("ALL");
  const [avail, setAvail] = useState<AvailFilter>("ALL");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [messageTarget, setMessageTarget] = useState<ProviderListItem | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    try {
      const params: { is_approved?: boolean; is_available?: boolean } = {};
      if (approval === "APPROVED") params.is_approved = true;
      if (approval === "PENDING")  params.is_approved = false;
      if (avail === "AVAILABLE")   params.is_available = true;
      if (avail === "OFFLINE")     params.is_available = false;

      const resp = await providersApi.list(params);
      setItems(resp.items);
      setError(null);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Could not load providers.");
    } finally {
      setLoading(false);
    }
  }, [approval, avail]);

  useEffect(() => { void fetch(); }, [fetch]);

  async function approve(p: ProviderListItem) {
    setBusyId(p.id);
    try {
      await adminApi.approveProvider(p.id);
      await fetch();
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Approve failed.");
    } finally {
      setBusyId(null);
    }
  }

  async function suspend(p: ProviderListItem) {
    const reason = prompt(`Suspend ${p.name}? Enter a reason (optional):`, "");
    if (reason === null) return;
    setBusyId(p.id);
    try {
      await adminApi.suspendProvider(p.id, reason || undefined);
      await fetch();
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Suspend failed.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-4">
      <header className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Providers</h1>
          <p className="text-sm text-slate-500">{items.length} shown</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            className="input max-w-[160px]"
            value={approval}
            onChange={(e) => setApproval(e.target.value as ApprovalFilter)}
          >
            <option value="ALL">All approvals</option>
            <option value="APPROVED">Approved</option>
            <option value="PENDING">Pending approval</option>
          </select>
          <select
            className="input max-w-[160px]"
            value={avail}
            onChange={(e) => setAvail(e.target.value as AvailFilter)}
          >
            <option value="ALL">Any availability</option>
            <option value="AVAILABLE">Available</option>
            <option value="OFFLINE">Offline</option>
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
                <th className="table-th">Name</th>
                <th className="table-th">Phone</th>
                <th className="table-th">Service</th>
                <th className="table-th">Approved</th>
                <th className="table-th">Available</th>
                <th className="table-th">Jobs</th>
                <th className="table-th">Last Ping</th>
                <th className="table-th text-right pr-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 && !loading && (
                <tr>
                  <td colSpan={8} className="px-3 py-10 text-center text-slate-500 text-sm">
                    No providers match these filters.
                  </td>
                </tr>
              )}
              {items.map((p) => (
                <tr key={p.id} className="hover:bg-slate-50">
                  <td className="table-td font-medium text-slate-900">{p.name}</td>
                  <td className="table-td font-mono text-xs">{p.phone}</td>
                  <td className="table-td">{p.service_type}</td>
                  <td className="table-td">
                    {p.is_approved
                      ? <span className="text-emerald-700 text-xs font-semibold">Yes</span>
                      : <span className="text-amber-700 text-xs font-semibold">Pending</span>}
                  </td>
                  <td className="table-td">
                    {p.is_available
                      ? <span className="text-emerald-700 text-xs font-semibold">Online</span>
                      : <span className="text-slate-500 text-xs">Offline</span>}
                  </td>
                  <td className="table-td">{p.total_jobs}</td>
                  <td className="table-td text-xs text-slate-500">
                    {p.last_ping ? new Date(p.last_ping).toLocaleString() : "never"}
                  </td>
                  <td className="table-td text-right pr-3">
                    <div className="inline-flex gap-1.5 justify-end">
                      {!p.is_approved && (
                        <button
                          onClick={() => approve(p)}
                          className="btn-success text-xs py-1.5 px-2.5"
                          disabled={busyId === p.id}
                        >
                          Approve
                        </button>
                      )}
                      <button
                        onClick={() => setMessageTarget(p)}
                        className="btn-secondary text-xs py-1.5 px-2.5"
                      >
                        Message
                      </button>
                      <button
                        onClick={() => suspend(p)}
                        className="btn-danger text-xs py-1.5 px-2.5"
                        disabled={busyId === p.id}
                      >
                        Suspend
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {messageTarget && (
        <NotifyModal
          provider={messageTarget}
          onClose={() => setMessageTarget(null)}
        />
      )}
    </div>
  );
}

function NotifyModal({
  provider, onClose,
}: {
  provider: ProviderListItem;
  onClose: () => void;
}) {
  const [body, setBody] = useState("");
  const [channel, setChannel] = useState<"sms" | "whatsapp">("sms");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setResult(null);
    setError(null);
    try {
      const resp = await adminApi.notify({
        to_phone: provider.phone,
        body,
        channel,
      });
      setResult(
        resp.twilio_sid
          ? `Sent (Twilio SID ${resp.twilio_sid})`
          : `Sent (logged locally — Twilio not configured)`
      );
      setBody("");
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Send failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-40 bg-slate-900/50 flex items-start justify-center p-4 overflow-y-auto"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg bg-white rounded-xl shadow-xl my-8"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between gap-3 px-5 py-4 border-b border-slate-100">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">
              Message {provider.name}
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">{provider.phone}</p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700 text-2xl leading-none px-2">×</button>
        </header>
        <form onSubmit={onSubmit} className="px-5 py-4 space-y-3">
          <div>
            <label className="label">Channel</label>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setChannel("sms")}
                className={channel === "sms" ? "btn-primary text-sm" : "btn-secondary text-sm"}
              >
                SMS
              </button>
              <button
                type="button"
                onClick={() => setChannel("whatsapp")}
                className={channel === "whatsapp" ? "btn-primary text-sm" : "btn-secondary text-sm"}
              >
                WhatsApp
              </button>
            </div>
          </div>
          <div>
            <label className="label" htmlFor="body">Message</label>
            <textarea
              id="body" className="input min-h-[120px]"
              maxLength={1000}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              required
            />
            <p className="mt-1 text-xs text-slate-500">{body.length} / 1000</p>
          </div>
          {result && <p className="text-xs text-emerald-700">{result}</p>}
          {error && <p className="text-xs text-rose-700">{error}</p>}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={onClose} className="btn-secondary text-sm">Close</button>
            <button type="submit" className="btn-primary text-sm" disabled={busy || body.trim().length === 0}>
              {busy ? "Sending…" : "Send"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
