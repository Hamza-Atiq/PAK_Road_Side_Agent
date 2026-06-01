import { useState, FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AuthShell } from "@/components/AuthShell";
import { authApi } from "@/lib/api";
import { useAuthStore } from "@/store/auth";

export function VerifyOTP({ role }: { role: "customer" | "provider" }) {
  const navigate = useNavigate();
  const setSession = useAuthStore((s) => s.setSession);
  const [params] = useSearchParams();
  const phone = params.get("phone") ?? "";
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const resp = await authApi.verifyOtp(phone, code.trim());
      setSession({ accessToken: resp.access_token, user: resp.user });
      navigate(
        role === "provider" ? "/provider" : "/customer/onboarding",
        { replace: true },
      );
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "Verification failed. Check the code.";
      setError(typeof msg === "string" ? msg : "Verification failed.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell
      role={role}
      title="Enter the code"
      subtitle={
        phone
          ? `We sent a 6-digit code to ${phone}. Code 000000 works in dev mode.`
          : "Enter the 6-digit code we just sent."
      }
    >
      <form onSubmit={onSubmit} className="space-y-4">
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Verification code</span>
          <input
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            placeholder="123456"
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-3 text-center text-2xl tracking-[0.5em] text-slate-900 shadow-sm transition focus:border-brand-customer focus:outline-none focus:ring-2 focus:ring-brand-customer/30"
            required
          />
        </label>
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        )}
        <button
          type="submit"
          disabled={submitting || code.length !== 6}
          className={
            role === "provider"
              ? "w-full rounded-xl bg-brand-provider px-6 py-3 font-semibold text-white shadow-md transition hover:bg-brand-provider-dark disabled:opacity-60"
              : "w-full rounded-xl bg-brand-customer px-6 py-3 font-semibold text-white shadow-md transition hover:bg-brand-customer-dark disabled:opacity-60"
          }
        >
          {submitting ? "Verifying…" : "Verify and continue"}
        </button>
      </form>
    </AuthShell>
  );
}
