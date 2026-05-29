import { FormEvent, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { authApi } from "@/api/auth";
import { useAuthStore } from "@/store/auth";
import { AuthShell } from "./Login";

export function VerifyOTP() {
  const navigate = useNavigate();
  const setSession = useAuthStore((s) => s.setSession);
  const location = useLocation();
  const initialPhone = (location.state as { phone?: string } | null)?.phone ?? "";
  const [phone, setPhone] = useState(initialPhone);
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const data = await authApi.verifyOtp(phone.trim(), code.trim());
      setSession({ accessToken: data.access_token, user: data.user });
      navigate("/report");
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Verification failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell
      title="Verify your phone"
      subtitle="Enter the code we sent to your number"
    >
      <form onSubmit={onSubmit} className="space-y-4">
        <div>
          <label className="label" htmlFor="phone">Phone</label>
          <input
            id="phone"
            className="input"
            type="tel"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            required
          />
        </div>
        <div>
          <label className="label" htmlFor="code">Code</label>
          <input
            id="code"
            className="input tracking-widest text-center text-lg"
            inputMode="numeric"
            maxLength={10}
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            required
            autoFocus
          />
          <p className="mt-1 text-xs text-slate-500">
            Dev mode: if you haven't configured Twilio Verify, use{" "}
            <code className="text-slate-700 font-mono">000000</code>.
          </p>
        </div>
        {error && <p className="text-sm text-rose-600">{error}</p>}
        <button type="submit" className="btn-primary w-full" disabled={loading}>
          {loading ? "Verifying…" : "Verify and continue"}
        </button>
      </form>
    </AuthShell>
  );
}
