import { FormEvent, useCallback, useEffect, useState } from "react";
import { adminApi } from "@/api/admin";
import type { AdminQueryResponse, DashboardResponse } from "@/types/api";

export function Metrics() {
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    try {
      setData(await adminApi.dashboard());
      setError(null);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Could not load dashboard.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetch();
    const t = setInterval(fetch, 30_000);
    return () => clearInterval(t);
  }, [fetch]);

  const grafanaUrl = import.meta.env.VITE_GRAFANA_EMBED_URL || "";

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Metrics & insights</h1>
          {data && (
            <p className="text-sm text-slate-500">
              Snapshot taken {new Date(data.generated_at).toLocaleString()}
            </p>
          )}
        </div>
        <button onClick={() => void fetch()} className="btn-secondary text-sm">Refresh</button>
      </header>

      {error && (
        <div className="card border-l-4 border-rose-400 bg-rose-50 text-sm text-rose-900">{error}</div>
      )}

      {loading && !data && (
        <div className="card animate-pulse"><div className="h-5 w-40 bg-slate-200 rounded" /></div>
      )}

      {data && (
        <>
          <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Stat
              label="Open incidents"
              value={data.open_incidents_count}
              tone={data.open_incidents_count > 0 ? "active" : "muted"}
            />
            <Stat label="Last 24h volume" value={data.incident_counts_24h} />
            <Stat
              label="Avg ETA (24h)"
              value={data.avg_eta_minutes_24h != null ? `${data.avg_eta_minutes_24h.toFixed(1)}m` : "—"}
            />
            <Stat
              label="Msg delivery rate"
              value={`${(data.messaging.delivery_rate * 100).toFixed(1)}%`}
              tone={data.messaging.delivery_rate < 0.95 ? "warn" : "muted"}
            />
          </section>

          <section>
            <h2 className="font-semibold text-slate-900 mb-2">Incidents by status</h2>
            <div className="grid grid-cols-3 md:grid-cols-5 gap-2">
              {Object.entries(data.incidents_by_status).map(([k, v]) => {
                const alert = (k === "NO_PROVIDER" || k === "ESCALATED") && v > 0;
                return (
                  <div
                    key={k}
                    className={`card py-3 px-4 ${alert ? "ring-rose-300 bg-rose-50" : ""}`}
                  >
                    <p className="text-xs uppercase tracking-wide text-slate-500">{k}</p>
                    <p className={`text-2xl font-bold ${alert ? "text-rose-700" : "text-slate-900"}`}>
                      {v}
                    </p>
                  </div>
                );
              })}
            </div>
          </section>

          <section>
            <h2 className="font-semibold text-slate-900 mb-2">Providers</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Stat label="Approved (total)" value={data.providers.total_approved} />
              <Stat label="Available now" value={data.providers.available_now} tone="active" />
              <Stat label="Online pingers (<90s)" value={data.providers.online_pingers} />
              <Stat label="On active job" value={data.providers.on_active_job} />
            </div>
          </section>

          <section>
            <h2 className="font-semibold text-slate-900 mb-2">Messaging (last 24h)</h2>
            <div className="grid grid-cols-3 gap-3">
              <Stat label="Sent" value={data.messaging.total_24h} />
              <Stat label="Delivered" value={data.messaging.delivered_24h} tone="active" />
              <Stat
                label="Failed"
                value={data.messaging.failed_24h}
                tone={data.messaging.failed_24h > 0 ? "warn" : "muted"}
              />
            </div>
          </section>

          <NaturalLanguageQueryPanel />

          <section>
            <h2 className="font-semibold text-slate-900 mb-2">Grafana dashboard</h2>
            {grafanaUrl ? (
              <iframe
                title="Grafana — RoadSide System Overview"
                src={grafanaUrl}
                className="w-full rounded-xl ring-1 ring-slate-200 bg-white"
                style={{ minHeight: "640px" }}
              />
            ) : (
              <div className="card text-sm text-slate-600">
                <p>
                  No Grafana embed configured. Set
                  <code className="mx-1 px-1 py-0.5 bg-slate-100 rounded">VITE_GRAFANA_EMBED_URL</code>
                  in your <code className="mx-1 px-1 py-0.5 bg-slate-100 rounded">.env</code> to embed a dashboard
                  panel here.
                </p>
                <p className="mt-2">
                  In the meantime, Grafana is reachable directly at{" "}
                  <a href="http://localhost:3000" target="_blank" rel="noreferrer"
                     className="text-brand-700 font-medium">localhost:3000</a>
                  {" "}(default <code>admin/admin</code>).
                </p>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}

function Stat({
  label, value, tone = "muted",
}: {
  label: string;
  value: number | string;
  tone?: "muted" | "active" | "warn";
}) {
  const ring =
    tone === "active" ? "ring-brand-200" :
    tone === "warn"   ? "ring-amber-300 bg-amber-50" :
                        "ring-slate-200";
  const valueCls =
    tone === "warn" ? "text-amber-700" : "text-slate-900";
  return (
    <div className={`card ring-1 ${ring}`}>
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`text-2xl font-bold mt-1 ${valueCls}`}>{value}</p>
    </div>
  );
}

function NaturalLanguageQueryPanel() {
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<AdminQueryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await adminApi.query({ query }));
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Query failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h2 className="font-semibold text-slate-900 mb-2">Ask the AdminAgent</h2>
      <div className="card">
        <form onSubmit={onSubmit} className="flex flex-col sm:flex-row gap-2">
          <input
            className="input flex-1"
            placeholder={"e.g. \"How many incidents are stuck in NO_PROVIDER?\""}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            required
          />
          <button className="btn-primary text-sm whitespace-nowrap" disabled={busy || !query.trim()}>
            {busy ? "Asking…" : "Ask"}
          </button>
        </form>
        {error && <p className="mt-3 text-xs text-rose-700">{error}</p>}
        {result && (
          <div className="mt-4 space-y-2">
            <div className="flex items-center gap-2 text-xs">
              <span className="px-2 py-0.5 rounded bg-brand-100 text-brand-800 font-semibold">
                {result.intent}
              </span>
              {result.actioned && (
                <span className="px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 font-semibold">
                  Action taken
                </span>
              )}
            </div>
            <p className="text-sm text-slate-800">{result.summary}</p>
            {result.data && (
              <pre className="text-xs bg-slate-50 ring-1 ring-slate-200 rounded p-2 overflow-x-auto">
                {JSON.stringify(result.data, null, 2)}
              </pre>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
