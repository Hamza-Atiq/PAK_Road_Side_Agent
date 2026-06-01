import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { incidentsApi } from "@/lib/api";
import type { ServiceType } from "@roadside/types";

type Issue = { id: ServiceType; label: string; icon: string; subtitle: string };

const ISSUES: Issue[] = [
  { id: "tow", label: "Tow", icon: "🚛", subtitle: "Vehicle won't move" },
  { id: "battery", label: "Battery", icon: "🔋", subtitle: "Jump start needed" },
  { id: "tire", label: "Flat tire", icon: "🛞", subtitle: "Change or repair" },
  { id: "fuel", label: "Fuel", icon: "⛽", subtitle: "Out of gas / wrong fuel" },
  { id: "lockout", label: "Lockout", icon: "🔑", subtitle: "Keys locked inside" },
  { id: "other", label: "Other", icon: "🆘", subtitle: "Describe the issue" },
];

export function ReportIncident() {
  const navigate = useNavigate();
  const [issue, setIssue] = useState<ServiceType | null>(null);
  const [description, setDescription] = useState("");
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [locError, setLocError] = useState<string | null>(null);
  const [image, setImage] = useState<File | null>(null);
  const [voice, setVoice] = useState<Blob | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!("geolocation" in navigator)) {
      setLocError("Your browser does not support geolocation.");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => setCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      (err) => setLocError(err.message || "Location unavailable"),
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  }, []);

  const submit = async () => {
    if (!issue || !coords) return;
    setError(null);
    setSubmitting(true);
    try {
      const resp = await incidentsApi.create({
        lat: coords.lat,
        lng: coords.lng,
        description: description.trim() || undefined,
        service_type: issue,
        image,
        voice,
      });
      navigate(`/customer/incidents/${resp.id}`, { replace: true });
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "Could not submit. Please try again.";
      setError(typeof msg === "string" ? msg : "Could not submit.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl">
      <TrustStrip />

      <section className="mt-6">
        <h1 className="text-2xl font-bold text-slate-900">What happened?</h1>
        <p className="mt-1 text-sm text-slate-600">Tap the issue. We&apos;ll do the rest.</p>
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
          {ISSUES.map((it) => (
            <button
              key={it.id}
              onClick={() => setIssue(it.id)}
              className={`flex flex-col items-start gap-1 rounded-2xl border-2 px-4 py-4 text-left transition ${
                issue === it.id
                  ? "border-brand-customer bg-brand-customer/5 shadow-md"
                  : "border-slate-200 bg-white hover:border-slate-300"
              }`}
            >
              <span className="text-3xl" aria-hidden>
                {it.icon}
              </span>
              <span className="text-base font-semibold text-slate-900">{it.label}</span>
              <span className="text-xs text-slate-500">{it.subtitle}</span>
            </button>
          ))}
        </div>
      </section>

      {issue && (
        <>
          <section className="mt-8">
            <h2 className="text-lg font-semibold text-slate-900">Your location</h2>
            <div className="mt-2 rounded-2xl border border-slate-200 bg-white p-4">
              {coords ? (
                <div className="flex items-center gap-3">
                  <span aria-hidden className="text-2xl">📍</span>
                  <div className="flex-1">
                    <div className="text-sm font-medium text-slate-900">
                      {coords.lat.toFixed(5)}, {coords.lng.toFixed(5)}
                    </div>
                    <div className="text-xs text-slate-500">
                      Accurate to within a few meters
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-sm text-amber-700">
                  {locError ?? "Getting your location…"}
                </div>
              )}
            </div>
          </section>

          <section className="mt-8">
            <h2 className="text-lg font-semibold text-slate-900">
              Add details <span className="text-xs font-normal text-slate-500">(optional)</span>
            </h2>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Anything we should know — strange noises, smoke, anything that might help."
              maxLength={500}
              rows={3}
              className="mt-2 w-full resize-none rounded-2xl border border-slate-300 px-4 py-3 text-sm text-slate-900 shadow-sm transition focus:border-brand-customer focus:outline-none focus:ring-2 focus:ring-brand-customer/30"
            />

            <div className="mt-3 grid grid-cols-2 gap-3">
              <PhotoCapture image={image} onChange={setImage} />
              <VoiceRecorder voice={voice} onChange={setVoice} />
            </div>
          </section>

          {error && (
            <div className="mt-6 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          )}

          <div className="sticky bottom-4 mt-8">
            <button
              onClick={submit}
              disabled={!coords || submitting}
              className="btn-emergency w-full text-xl shadow-2xl shadow-emergency/40"
            >
              {submitting ? "Sending…" : "🆘 Get help now"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function TrustStrip() {
  return (
    <div className="grid grid-cols-3 gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-xs sm:text-sm">
      <span className="flex items-center gap-1.5 text-slate-700">
        <span aria-hidden>🛡️</span> Verified providers
      </span>
      <span className="flex items-center gap-1.5 text-slate-700">
        <span aria-hidden>📍</span> Live tracked
      </span>
      <span className="flex items-center gap-1.5 text-slate-700">
        <span aria-hidden>💳</span> No charge unless help arrives
      </span>
    </div>
  );
}

function PhotoCapture({
  image,
  onChange,
}: {
  image: File | null;
  onChange: (f: File | null) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  return (
    <div>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={(e) => onChange(e.target.files?.[0] ?? null)}
      />
      <button
        onClick={() => inputRef.current?.click()}
        className={`flex w-full items-center justify-center gap-2 rounded-xl border-2 px-4 py-3 font-medium transition ${
          image
            ? "border-brand-customer bg-brand-customer/5 text-brand-customer-dark"
            : "border-dashed border-slate-300 text-slate-700 hover:border-slate-400"
        }`}
      >
        <span aria-hidden>📷</span>
        {image ? "Photo added ✓" : "Add photo"}
      </button>
    </div>
  );
}

function VoiceRecorder({
  voice,
  onChange,
}: {
  voice: Blob | null;
  onChange: (b: Blob | null) => void;
}) {
  const [recording, setRecording] = useState(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const toggle = async () => {
    if (recording) {
      recorderRef.current?.stop();
      setRecording(false);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream, { mimeType: "audio/webm" });
      chunksRef.current = [];
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      rec.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        onChange(blob);
        stream.getTracks().forEach((t) => t.stop());
      };
      rec.start();
      recorderRef.current = rec;
      setRecording(true);
    } catch {
      onChange(null);
    }
  };

  return (
    <button
      onClick={toggle}
      className={`flex w-full items-center justify-center gap-2 rounded-xl border-2 px-4 py-3 font-medium transition ${
        recording
          ? "border-emergency bg-emergency/5 text-emergency"
          : voice
            ? "border-brand-customer bg-brand-customer/5 text-brand-customer-dark"
            : "border-dashed border-slate-300 text-slate-700 hover:border-slate-400"
      }`}
    >
      <span aria-hidden>{recording ? "⏺" : "🎙️"}</span>
      {recording ? "Tap to stop" : voice ? "Voice added ✓" : "Add voice note"}
    </button>
  );
}
