import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { authApi } from "@/api/auth";
import { useAuthStore } from "@/store/auth";
import { normalizePhone } from "@/hooks/usePhoneInput";

export function Login() {
  const navigate = useNavigate();
  const setSession = useAuthStore((s) => s.setSession);
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const normalized = normalizePhone(phone);
    if (!normalized) {
      setError("Please enter a valid international phone number, e.g. +15551234567");
      return;
    }
    setLoading(true);
    try {
      const data = await authApi.login(normalized, password);
      if (data.user.role !== "provider") {
        setError("This panel is for providers only.");
        return;
      }
      setSession({ accessToken: data.access_token, user: data.user });
      navigate("/dashboard");
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      if (err?.response?.status === 403 && String(detail).toLowerCase().includes("verified")) {
        navigate("/verify-otp", { state: { phone: normalized } });
        return;
      }
      setError(detail || "Sign in failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell title="Provider sign-in" subtitle="Get back on the road">
      <form onSubmit={onSubmit} className="space-y-4">
        <div>
          <label className="label" htmlFor="phone">Phone</label>
          <input
            id="phone" type="tel" className="input"
            placeholder="+15551234567"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            autoComplete="tel" required
          />
        </div>
        <div>
          <label className="label" htmlFor="password">Password</label>
          <input
            id="password" type="password" className="input"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password" required
          />
        </div>
        {error && <p className="text-sm text-rose-600">{error}</p>}
        <button type="submit" className="btn-primary w-full" disabled={loading}>
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>
      <p className="mt-6 text-center text-sm text-slate-600">
        New provider?{" "}
        <Link to="/register" className="text-brand-700 font-medium">
          Apply to join
        </Link>
      </p>
    </AuthShell>
  );
}

export function AuthShell({
  title, subtitle, children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-full grid place-items-center px-4 py-10 bg-gradient-to-b from-slate-50 to-slate-100">
      <div className="w-full max-w-md">
        <div className="text-center mb-6">
          <span className="inline-block h-10 w-10 rounded-lg bg-brand-600 text-white grid place-items-center font-bold mb-3">
            P
          </span>
          <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-slate-600">{subtitle}</p>}
        </div>
        <div className="card">{children}</div>
      </div>
    </div>
  );
}
