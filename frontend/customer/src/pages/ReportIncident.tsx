import { FormEvent, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { MapView } from "@/components/MapView";
import { useGeolocation } from "@/hooks/useGeolocation";
import { incidentsApi } from "@/api/incidents";

// Default center used while we wait for browser GPS. Picks a globally-sensible
// fallback (Greenwich, 0° meridian) — never region-biased.
const FALLBACK_LAT = 51.4778;
const FALLBACK_LNG = 0.0014;

export function ReportIncident() {
  const navigate = useNavigate();
  const geo = useGeolocation();
  const [lat, setLat] = useState<number>(FALLBACK_LAT);
  const [lng, setLng] = useState<number>(FALLBACK_LNG);
  const [hasUserLocation, setHasUserLocation] = useState(false);
  const [description, setDescription] = useState("");
  const [address, setAddress] = useState("");
  const [image, setImage] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [voiceBlob, setVoiceBlob] = useState<Blob | null>(null);
  const [recording, setRecording] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Request browser GPS once on mount; user can also tap the button to retry
  useEffect(() => {
    geo.request();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (geo.position && !hasUserLocation) {
      setLat(geo.position.lat);
      setLng(geo.position.lng);
      setHasUserLocation(true);
    }
  }, [geo.position, hasUserLocation]);

  // ---------- Image upload ----------
  function onImageChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] ?? null;
    setImage(file);
    if (imagePreview) URL.revokeObjectURL(imagePreview);
    setImagePreview(file ? URL.createObjectURL(file) : null);
  }

  // ---------- Voice recording ----------
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recordedChunksRef = useRef<Blob[]>([]);

  async function startRecording() {
    setError(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("Voice recording isn't supported in this browser.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      recordedChunksRef.current = [];
      mr.ondataavailable = (e) => {
        if (e.data.size > 0) recordedChunksRef.current.push(e.data);
      };
      mr.onstop = () => {
        const blob = new Blob(recordedChunksRef.current, {
          type: mr.mimeType || "audio/webm",
        });
        setVoiceBlob(blob);
        stream.getTracks().forEach((t) => t.stop());
      };
      mr.start();
      mediaRecorderRef.current = mr;
      setRecording(true);
    } catch (err: any) {
      setError(err?.message || "Microphone permission denied.");
    }
  }

  function stopRecording() {
    mediaRecorderRef.current?.stop();
    mediaRecorderRef.current = null;
    setRecording(false);
  }

  function clearVoice() {
    setVoiceBlob(null);
  }

  // ---------- Submit ----------
  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!description && !image && !voiceBlob) {
      setError("Please describe the issue, attach a photo, or record a voice note.");
      return;
    }
    setSubmitting(true);
    try {
      const resp = await incidentsApi.create({
        lat, lng,
        description: description.trim() || undefined,
        address: address.trim() || undefined,
        image,
        voice: voiceBlob,
      });
      navigate(`/incidents/${resp.id}`);
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Could not submit your report.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
      <div className="lg:col-span-3 space-y-4">
        <div className="card">
          <h1 className="text-xl font-semibold text-slate-900">
            Report a breakdown
          </h1>
          <p className="text-sm text-slate-600 mt-1">
            Drop your pin, describe the issue. We'll dispatch the nearest help.
          </p>
        </div>

        <div className="card p-0 overflow-hidden">
          <MapView
            lat={lat}
            lng={lng}
            editable
            onMove={(la, ln) => {
              setLat(la);
              setLng(ln);
              setHasUserLocation(true);
            }}
            height="380px"
          />
          <div className="px-4 py-3 flex flex-wrap items-center justify-between gap-3 border-t border-slate-200">
            <div className="text-xs text-slate-600">
              {hasUserLocation ? (
                <>
                  Location: <code className="text-slate-800">
                    {lat.toFixed(5)}, {lng.toFixed(5)}
                  </code>
                </>
              ) : (
                <span className="text-amber-600">
                  Waiting for location — drag the pin or use the button.
                </span>
              )}
            </div>
            <button
              type="button"
              onClick={geo.request}
              disabled={geo.loading}
              className="btn-secondary text-sm"
            >
              {geo.loading ? "Locating…" : "Use my location"}
            </button>
          </div>
          {geo.error && (
            <p className="px-4 pb-3 text-xs text-rose-600">{geo.error}</p>
          )}
        </div>
      </div>

      <form onSubmit={onSubmit} className="lg:col-span-2 card space-y-4">
        <div>
          <label className="label" htmlFor="address">Address (optional)</label>
          <input
            id="address"
            className="input"
            placeholder="123 Main St, San Francisco"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
          />
        </div>

        <div>
          <label className="label" htmlFor="description">What's wrong?</label>
          <textarea
            id="description"
            className="input min-h-[110px]"
            placeholder="e.g. flat tire on highway, smoke from the hood, battery won't start"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>

        <div>
          <span className="label">Photo (optional)</span>
          <label className="btn-secondary cursor-pointer w-full">
            <input
              type="file"
              accept="image/*"
              className="hidden"
              onChange={onImageChange}
            />
            {image ? `Replace: ${image.name}` : "Choose photo"}
          </label>
          {imagePreview && (
            <img
              src={imagePreview}
              alt="preview"
              className="mt-2 rounded-lg border border-slate-200 max-h-48 mx-auto"
            />
          )}
        </div>

        <div>
          <span className="label">Voice note (optional)</span>
          <div className="flex items-center gap-2">
            {recording ? (
              <button
                type="button"
                onClick={stopRecording}
                className="btn-danger flex-1"
              >
                ⏹ Stop recording
              </button>
            ) : (
              <button
                type="button"
                onClick={startRecording}
                className="btn-secondary flex-1"
              >
                🎙 Record voice note
              </button>
            )}
            {voiceBlob && !recording && (
              <button
                type="button"
                onClick={clearVoice}
                className="btn-secondary"
                title="Discard recording"
              >
                ✕
              </button>
            )}
          </div>
          {voiceBlob && !recording && (
            <audio
              controls
              className="mt-2 w-full"
              src={URL.createObjectURL(voiceBlob)}
            />
          )}
        </div>

        {error && <p className="text-sm text-rose-600">{error}</p>}

        <button
          type="submit"
          className="btn-primary w-full"
          disabled={submitting}
        >
          {submitting ? "Sending help…" : "Send help"}
        </button>
      </form>
    </div>
  );
}
