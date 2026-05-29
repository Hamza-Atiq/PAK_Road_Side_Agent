import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { authApi } from "@/api/auth";
import { normalizePhone } from "@/hooks/usePhoneInput";
import { AuthShell } from "./Login";

const SERVICE_TYPES = [
  { value: "mechanic", label: "Mechanic" },
  { value: "tow_truck", label: "Tow truck" },
  { value: "tire", label: "Tire service" },
  { value: "battery", label: "Battery / jump-start" },
  { value: "fuel", label: "Fuel delivery" },
  { value: "locksmith", label: "Locksmith" },
  { value: "other", label: "Other" },
];

export function Register() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [serviceType, setServiceType] = useState("mechanic");
  const [vehicleInfo, setVehicleInfo] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const normalized = normalizePhone(phone);
    if (!normalized) {
      setError("Please enter a valid international phone number.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setLoading(true);
    try {
      await authApi.register({
        name: name.trim(),
        phone: normalized,
        password,
        role: "provider",
        service_type: serviceType,
        vehicle_info: vehicleInfo.trim() || undefined,
        email: email.trim() || undefined,
      });
      navigate("/verify-otp", { state: { phone: normalized } });
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Registration failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell
      title="Apply to join"
      subtitle="After signup, admin reviews your account before you can take jobs"
    >
      <form onSubmit={onSubmit} className="space-y-4">
        <div>
          <label className="label" htmlFor="name">Full name</label>
          <input id="name" className="input" required
            value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="phone">Phone</label>
          <input id="phone" className="input" type="tel" required
            placeholder="+15551234567"
            value={phone} onChange={(e) => setPhone(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="email">Email (optional)</label>
          <input id="email" className="input" type="email"
            value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="password">Password</label>
          <input id="password" className="input" type="password" required minLength={8}
            value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="service_type">Service type</label>
          <select
            id="service_type"
            className="input"
            value={serviceType}
            onChange={(e) => setServiceType(e.target.value)}
          >
            {SERVICE_TYPES.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="vehicle">Vehicle / equipment</label>
          <textarea id="vehicle" className="input"
            placeholder="e.g. 2022 Ford F-450 — 10t tow capacity"
            value={vehicleInfo} onChange={(e) => setVehicleInfo(e.target.value)} />
        </div>
        {error && <p className="text-sm text-rose-600">{error}</p>}
        <button type="submit" className="btn-primary w-full" disabled={loading}>
          {loading ? "Submitting…" : "Submit application"}
        </button>
      </form>
      <p className="mt-6 text-center text-sm text-slate-600">
        Already registered?{" "}
        <Link to="/login" className="text-brand-700 font-medium">Sign in</Link>
      </p>
    </AuthShell>
  );
}
