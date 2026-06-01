import { useState, FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AuthShell } from "@/components/AuthShell";
import { SocialSignIn } from "@/components/SocialSignIn";
import { authApi } from "@/lib/api";

export function Register({ role }: { role: "customer" | "provider" }) {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await authApi.register({
        phone: phone.trim(),
        name: name.trim(),
        password,
        role,
      });
      navigate(
        `${role === "provider" ? "/provider" : "/customer"}/verify-otp?phone=${encodeURIComponent(phone.trim())}`,
        { replace: true },
      );
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "Registration failed. Check your details and try again.";
      setError(typeof msg === "string" ? msg : "Registration failed.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell
      role={role}
      title={role === "provider" ? "Sign up to provide help" : "Sign up to get help"}
      subtitle="It takes about 60 seconds."
      footer={
        <>
          Already have an account?{" "}
          <Link
            to={role === "provider" ? "/provider/login" : "/customer/login"}
            className="font-semibold text-slate-900 underline-offset-4 hover:underline"
          >
            Sign in
          </Link>
        </>
      }
    >
      <SocialSignIn role={role} />

      <div className="my-5 flex items-center gap-3">
        <div className="h-px flex-1 bg-slate-200" />
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          or with phone
        </span>
        <div className="h-px flex-1 bg-slate-200" />
      </div>

      <form onSubmit={onSubmit} className="space-y-4">
        <Field
          label="Your name"
          type="text"
          autoComplete="name"
          value={name}
          onChange={setName}
          placeholder="Hamza Atiq"
          required
        />
        <Field
          label="Phone number"
          type="tel"
          autoComplete="tel"
          value={phone}
          onChange={setPhone}
          placeholder="+1 555 000 0001"
          required
        />
        <Field
          label="Password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={setPassword}
          placeholder="At least 8 characters"
          minLength={8}
          required
        />
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        )}
        <button
          type="submit"
          disabled={submitting}
          className={
            role === "provider"
              ? "w-full rounded-xl bg-brand-provider px-6 py-3 font-semibold text-white shadow-md transition hover:bg-brand-provider-dark disabled:opacity-60"
              : "w-full rounded-xl bg-brand-customer px-6 py-3 font-semibold text-white shadow-md transition hover:bg-brand-customer-dark disabled:opacity-60"
          }
        >
          {submitting ? "Creating account…" : "Send verification code"}
        </button>
      </form>
    </AuthShell>
  );
}

function Field({
  label,
  value,
  onChange,
  ...rest
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
} & Omit<React.InputHTMLAttributes<HTMLInputElement>, "value" | "onChange">) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-slate-700">{label}</span>
      <input
        {...rest}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-slate-900 shadow-sm transition focus:border-brand-customer focus:outline-none focus:ring-2 focus:ring-brand-customer/30"
      />
    </label>
  );
}
