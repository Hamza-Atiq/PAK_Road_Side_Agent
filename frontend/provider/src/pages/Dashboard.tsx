import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { providersApi } from "@/api/providers";
import { incidentsApi } from "@/api/incidents";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useGpsBeacon } from "@/hooks/useGpsBeacon";
import { useAuthStore } from "@/store/auth";
import type { IncidentBrief, ProviderProfile } from "@/types/api";

// Short alert tone, generated via Web Audio API so we don't have to ship
// an audio asset. ~250ms beep at ~880 Hz.
function playAlertTone() {
  try {
    const AudioCtx =
      (window as any).AudioContext || (window as any).webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = 880;
    gain.gain.value = 0.15;
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    setTimeout(() => {
      osc.stop();
      ctx.close();
    }, 250);
  } catch {
    /* audio is best-effort */
  }
}

export function Dashboard() {
  const user = useAuthStore((s) => s.user);
  const [profile, setProfile] = useState<ProviderProfile | null>(null);
  const [assigned, setAssigned] = useState<IncidentBrief[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toggleBusy, setToggleBusy] = useState(false);
  const [newJobBanner, setNewJobBanner] = useState<string | null>(null);
  const knownJobIdsRef = useRef<Set<string>>(new Set());

  const refetch = useCallback(async () => {
    try {
      const [p, a] = await Promise.all([
        providersApi.me(),
        incidentsApi.listAssigned(),
      ]);
      setProfile(p);
      // Detect newly-assigned jobs (not seen on previous load) → beep + banner
      for (const job of a.items) {
        if (!knownJobIdsRef.current.has(job.id)) {
          // Only alert after we've seen at least one load (not the initial mount)
          if (knownJobIdsRef.current.size > 0 || (profile && a.items.length > 0)) {
            playAlertTone();
            setNewJobBanner(`New job assigned: ${job.id.slice(0, 8)}…`);
            setTimeout(() => setNewJobBanner(null), 8000);
          }
        }
      }
      knownJobIdsRef.current = new Set(a.items.map((i) => i.id));
      setAssigned(a.items);
      setError(null);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Could not load dashboard.");
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    refetch();
    const t = setInterval(refetch, 20_000);
    return () => clearInterval(t);
  }, [refetch]);

  // Admin firehose for live updates — providers don't have their own stream,
  // but admin events include incident assignments which trigger our refetch.
  // (Fallback: the 20s poll above will catch anything WS misses.)
  // We subscribe per-incident as soon as we have one assigned.
  const wsPath = useMemo(() => {
    if (assigned.length === 0) return "";
    return `/ws/incidents/${assigned[0].id}`;
  }, [assigned]);

  useWebSocket({
    path: wsPath,
    enabled: !!wsPath,
    onEvent: () => void refetch(),
  });

  // GPS beacon: only ping when both approved AND available
  const beaconEnabled = !!profile && profile.is_approved && profile.is_available;
  const beacon = useGpsBeacon({
    enabled: beaconEnabled,
    intervalMs: 30_000,
  });

  async function toggleAvailability(next: boolean) {
    if (!profile) return;
    setToggleBusy(true);
    try {
      const updated = await providersApi.setAvailability(next);
      setProfile(updated);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Could not change availability.");
    } finally {
      setToggleBusy(false);
    }
  }

  if (loading) {
    return <div className="card animate-pulse"><div className="h-5 w-40 bg-slate-200 rounded" /></div>;
  }
  if (error && !profile) {
    return <div className="card"><p className="text-sm text-rose-600">{error}</p></div>;
  }
  if (!profile) return null;

  return (
    <div className="space-y-4">
      {newJobBanner && (
        <div className="rounded-lg bg-brand-50 ring-1 ring-brand-200 px-4 py-3 text-sm text-brand-900 flex items-center justify-between">
          <span>🔔 {newJobBanner}</span>
          <button
            onClick={() => setNewJobBanner(null)}
            className="text-brand-700 font-medium"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Approval gate */}
      {!profile.is_approved && (
        <div className="card border-l-4 border-amber-400 bg-amber-50">
          <h2 className="font-semibold text-amber-900">Awaiting admin approval</h2>
          <p className="mt-1 text-sm text-amber-800">
            Your account is registered but not yet approved. You can't accept
            jobs or go online until an admin reviews your profile.
          </p>
        </div>
      )}

      {/* Availability + GPS card */}
      <div className="card">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h2 className="font-semibold text-slate-900">
              {user?.name}
            </h2>
            <p className="text-sm text-slate-600 mt-0.5">
              {profile.service_type} · {profile.total_jobs} jobs completed
            </p>
            <p className="text-xs text-slate-500 mt-1">
              Last GPS ping:{" "}
              {beacon.lastPingAt
                ? new Date(beacon.lastPingAt).toLocaleTimeString()
                : profile.last_ping
                ? new Date(profile.last_ping).toLocaleTimeString()
                : "never"}
              {beacon.inFlight && " (updating…)"}
            </p>
          </div>
          <button
            onClick={() => toggleAvailability(!profile.is_available)}
            disabled={!profile.is_approved || toggleBusy}
            className={
              profile.is_available
                ? "btn-danger min-w-[140px]"
                : "btn-primary min-w-[140px]"
            }
          >
            {toggleBusy
              ? "…"
              : profile.is_available
              ? "Go offline"
              : "Go online"}
          </button>
        </div>
        {beacon.error && (
          <p className="mt-3 text-xs text-rose-600">GPS: {beacon.error}</p>
        )}
      </div>

      {/* Active job */}
      <div>
        <h2 className="text-sm font-semibold text-slate-700 px-1 mb-2">
          Active job
        </h2>
        {assigned.length === 0 ? (
          <div className="card text-center text-slate-500 text-sm">
            {profile.is_available
              ? "Waiting for the next job…"
              : "Go online to start receiving jobs."}
          </div>
        ) : (
          <div className="space-y-2">
            {assigned.map((j) => (
              <Link
                key={j.id}
                to={`/jobs/${j.id}`}
                className="card flex items-center justify-between gap-3 hover:ring-brand-300 hover:shadow-md transition"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <StatusPill status={j.status} />
                    <span className="text-xs text-slate-500">
                      {new Date(j.created_at).toLocaleTimeString()}
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-slate-700">
                    {j.lat.toFixed(4)}, {j.lng.toFixed(4)}
                    {j.eta_minutes != null && (
                      <span className="ml-2 text-slate-500">
                        · ETA {j.eta_minutes} min
                      </span>
                    )}
                  </p>
                </div>
                <span className="text-slate-400 text-xl">→</span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const map: Record<string, string> = {
    ASSIGNED: "bg-indigo-100 text-indigo-800",
    EN_ROUTE: "bg-amber-100 text-amber-800",
    ARRIVED: "bg-violet-100 text-violet-800",
  };
  return (
    <span className={`text-[11px] font-medium px-2 py-0.5 rounded ${map[status] || "bg-slate-100 text-slate-700"}`}>
      {status}
    </span>
  );
}
