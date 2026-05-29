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
      if (data.user.role !== "provider") {
        setError("This account isn't a provider account.");
        return;
      }
      setSession({ accessToken: data.access_token, user: data.user });
      navigate("/dashboard");
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Verification failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell title="Verify your phone" subtitle="Enter the code we sent you">
      <form onSubmit={onSubmit} className="space-y-4">
        <div>
          <label className="label" htmlFor="phone">Phone</label>
          <input id="phone" type="tel" className="input" required
            value={phone} onChange={(e) => setPhone(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="code">Code</label>
          <input
            id="code" inputMode="numeric" maxLength={10}
            className="input tracking-widest text-center text-lg"
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            autoFocus required
          />
          <p className="mt-1 text-xs text-slate-500">
            Dev mode: use <code className="font-mono">000000</code>.
          </p>
        </div>
        {error && <p className="text-sm text-rose-600">{error}</p>}
        <button type="submit" className="btn-primary w-full" disabled={loading}>
          {loading ? "Verifying…" : "Verify"}
        </button>
      </form>
    </AuthShell>
  );
}
