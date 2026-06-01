import { useEffect, useState, useRef } from "react";
import { Link } from "react-router-dom";
import { incidentsApi, providersApi } from "@/lib/api";
import type { Incident, ProviderProfile } from "@roadside/api-client";

export function ProviderDashboard() {
  const [me, setMe] = useState<ProviderProfile | null>(null);
  const [jobs, setJobs] = useState<Incident[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [toggling, setToggling] = useState(false);
  const pingTimerRef = useRef<number | null>(null);

  // Load profile + assigned jobs
  useEffect(() => {
    let cancelled = false;
    Promise.all([providersApi.me(), incidentsApi.listAssigned(false)])
      .then(([p, j]) => {
        if (cancelled) return;
        setMe(p);
        setJobs(j.items);
      })
      .catch(() => !cancelled && setError("Could not load dashboard."));
    return () => {
      cancelled = true;
    };
  }, []);

  // GPS ping loop — every 30s while available
  useEffect(() => {
    if (!me?.is_available) {
      if (pingTimerRef.current) window.clearInterval(pingTimerRef.current);
      pingTimerRef.current = null;
      return;
    }
    if (!("geolocation" in navigator)) return;

    const ping = () => {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          providersApi
            .pingLocation(pos.coords.latitude, pos.coords.longitude)
            .catch(() => {});
        },
        () => {},
        { enableHighAccuracy: true, timeout: 8000 },
      );
    };
    ping();
    pingTimerRef.current = window.setInterval(ping, 30_000);
    return () => {
      if (pingTimerRef.current) window.clearInterval(pingTimerRef.current);
      pingTimerRef.current = null;
    };
  }, [me?.is_available]);

  // Poll jobs every 15s (cheap, complements WS)
  useEffect(() => {
    const t = window.setInterval(() => {
      incidentsApi
        .listAssigned(false)
        .then((j) => setJobs(j.items))
        .catch(() => {});
    }, 15_000);
    return () => window.clearInterval(t);
  }, []);

  const toggleAvailability = async () => {
    if (!me) return;
    setToggling(true);
    try {
      const updated = await providersApi.setAvailability(!me.is_available);
      setMe(updated);
    } finally {
      setToggling(false);
    }
  };

  if (error) {
    return <div className="mx-auto max-w-2xl py-10 text-center text-slate-600">{error}</div>;
  }
  if (!me) {
    return <div className="mx-auto max-w-2xl py-10 text-center text-slate-500">Loading…</div>;
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div className="flex flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Availability
          </div>
          <div className="mt-1 text-2xl font-bold text-slate-900">
            {me.is_available ? "Online" : "Offline"}
          </div>
          <div className="mt-1 text-sm text-slate-600">
            {me.is_available
              ? "You can receive nearby jobs. We're sharing your live location."
              : "Turn on to start receiving job assignments."}
          </div>
        </div>
        <button
          onClick={toggleAvailability}
          disabled={toggling}
          className={`relative inline-flex h-12 w-24 items-center rounded-full transition ${
            me.is_available ? "bg-brand-provider" : "bg-slate-300"
          } disabled:opacity-60`}
        >
          <span
            className={`inline-block h-10 w-10 transform rounded-full bg-white shadow transition ${
              me.is_available ? "translate-x-13" : "translate-x-1"
            }`}
            style={{ transform: me.is_available ? "translateX(56px)" : "translateX(4px)" }}
          />
        </button>
      </div>

      <Stats me={me} />

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-bold text-slate-900">Active jobs</h2>
          {jobs.length > 0 && (
            <span className="rounded-full bg-warning/10 px-2.5 py-0.5 text-xs font-semibold text-warning">
              {jobs.length} {jobs.length === 1 ? "job" : "jobs"}
            </span>
          )}
        </div>

        {jobs.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center">
            <div className="text-4xl">📡</div>
            <p className="mt-2 text-sm text-slate-600">
              {me.is_available
                ? "Listening for jobs nearby…"
                : "Turn on availability to start receiving jobs."}
            </p>
          </div>
        ) : (
          <ul className="space-y-2">
            {jobs.map((j) => (
              <li key={j.id}>
                <Link
                  to={`/provider/jobs/${j.id}`}
                  className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white p-4 transition hover:border-brand-provider hover:shadow-sm"
                >
                  <div className="text-2xl">{iconFor(j.service_type ?? "other")}</div>
                  <div className="flex-1">
                    <div className="font-semibold capitalize text-slate-900">
                      {j.service_type ?? "incident"}
                    </div>
                    <div className="text-xs text-slate-500">
                      Status: <span className="font-medium text-slate-700">{j.status}</span>
                    </div>
                  </div>
                  <span aria-hidden className="text-slate-400">→</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function Stats({ me }: { me: ProviderProfile }) {
  const items = [
    { label: "Jobs completed", value: me.jobs_completed ?? 0 },
    { label: "Rating", value: me.rating ? me.rating.toFixed(1) + " ★" : "—" },
    { label: "Status", value: me.verification_status ?? "active" },
  ];
  return (
    <div className="grid grid-cols-3 gap-3">
      {items.map((s) => (
        <div
          key={s.label}
          className="rounded-2xl border border-slate-200 bg-white p-4 text-center"
        >
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            {s.label}
          </div>
          <div className="mt-1 text-xl font-bold text-slate-900">{s.value}</div>
        </div>
      ))}
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
