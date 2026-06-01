import { useState, FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useOnboardingStore, type Vehicle } from "@/store/onboarding";

type Step = "welcome" | "location" | "vehicle" | "done";

export function Onboarding() {
  const navigate = useNavigate();
  const {
    setVehicle,
    markLocationRequested,
    completeOnboarding,
  } = useOnboardingStore();
  const [step, setStep] = useState<Step>("welcome");
  const [vehicle, setVehicleState] = useState<Vehicle>({
    make: "",
    model: "",
    year: "",
    color: "",
    plate: "",
  });
  const [locStatus, setLocStatus] = useState<"idle" | "asking" | "granted" | "denied">("idle");

  const askLocation = () => {
    setLocStatus("asking");
    if (!("geolocation" in navigator)) {
      setLocStatus("denied");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      () => {
        setLocStatus("granted");
        markLocationRequested();
      },
      () => {
        setLocStatus("denied");
        markLocationRequested();
      },
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  };

  const saveVehicle = (e: FormEvent) => {
    e.preventDefault();
    setVehicle(vehicle);
    setStep("done");
  };

  const finish = () => {
    completeOnboarding();
    navigate("/customer/report", { replace: true });
  };

  return (
    <div className="mx-auto flex max-w-md flex-col gap-6 py-6">
      <StepIndicator step={step} />

      {step === "welcome" && (
        <Card>
          <h2 className="text-2xl font-bold text-slate-900">Let&apos;s get you ready</h2>
          <p className="mt-2 text-slate-600">
            3 quick steps. We&apos;ll only ask for what we need so help can find you fast.
          </p>
          <ul className="mt-5 space-y-3 text-sm text-slate-700">
            <li className="flex items-center gap-3">
              <Dot n="1" /> Allow location so we know where to send help
            </li>
            <li className="flex items-center gap-3">
              <Dot n="2" /> Add your vehicle so providers come prepared
            </li>
            <li className="flex items-center gap-3">
              <Dot n="3" /> You&apos;re done — ready to request help
            </li>
          </ul>
          <button onClick={() => setStep("location")} className="btn-primary mt-6 w-full">
            Start
          </button>
        </Card>
      )}

      {step === "location" && (
        <Card>
          <h2 className="text-2xl font-bold text-slate-900">Location access</h2>
          <p className="mt-2 text-slate-600">
            We use your location to find the closest verified provider and to share a live tracking
            link with your family.
          </p>
          <div className="mt-6 space-y-3">
            <button onClick={askLocation} className="btn-primary w-full">
              {locStatus === "asking" ? "Requesting…" : "Allow location"}
            </button>
            {locStatus === "granted" && (
              <p className="text-center text-sm font-semibold text-success">
                ✓ Location enabled
              </p>
            )}
            {locStatus === "denied" && (
              <p className="text-center text-sm text-amber-700">
                You can enable location later in browser settings. We&apos;ll prompt again when you
                report an incident.
              </p>
            )}
            <button
              onClick={() => setStep("vehicle")}
              disabled={locStatus === "idle" || locStatus === "asking"}
              className="w-full rounded-xl border border-slate-300 px-6 py-3 font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              Continue
            </button>
          </div>
        </Card>
      )}

      {step === "vehicle" && (
        <Card>
          <h2 className="text-2xl font-bold text-slate-900">Your vehicle</h2>
          <p className="mt-2 text-slate-600">So the provider knows what to look for.</p>
          <form onSubmit={saveVehicle} className="mt-5 grid grid-cols-2 gap-3">
            <VehicleField
              span={1}
              label="Make"
              value={vehicle.make}
              onChange={(v) => setVehicleState({ ...vehicle, make: v })}
              placeholder="Toyota"
              required
            />
            <VehicleField
              span={1}
              label="Model"
              value={vehicle.model}
              onChange={(v) => setVehicleState({ ...vehicle, model: v })}
              placeholder="Corolla"
              required
            />
            <VehicleField
              span={1}
              label="Year"
              value={vehicle.year}
              onChange={(v) => setVehicleState({ ...vehicle, year: v })}
              placeholder="2019"
            />
            <VehicleField
              span={1}
              label="Color"
              value={vehicle.color}
              onChange={(v) => setVehicleState({ ...vehicle, color: v })}
              placeholder="Silver"
            />
            <VehicleField
              span={2}
              label="License plate"
              value={vehicle.plate}
              onChange={(v) => setVehicleState({ ...vehicle, plate: v })}
              placeholder="ABC-1234"
            />
            <div className="col-span-2 mt-2">
              <button type="submit" className="btn-primary w-full">
                Save vehicle
              </button>
            </div>
          </form>
        </Card>
      )}

      {step === "done" && (
        <Card>
          <div className="text-center">
            <div className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-success/10 text-3xl">
              ✓
            </div>
            <h2 className="mt-4 text-2xl font-bold text-slate-900">You&apos;re set</h2>
            <p className="mt-2 text-slate-600">
              When something goes wrong, you&apos;re one tap away from help.
            </p>
            <button onClick={finish} className="btn-primary mt-6 w-full">
              Go to home
            </button>
          </div>
        </Card>
      )}
    </div>
  );
}

function Card({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">{children}</div>
  );
}

function Dot({ n }: { n: string }) {
  return (
    <span className="grid h-7 w-7 place-items-center rounded-full bg-brand-customer/10 text-sm font-bold text-brand-customer">
      {n}
    </span>
  );
}

function StepIndicator({ step }: { step: Step }) {
  const order: Step[] = ["welcome", "location", "vehicle", "done"];
  const idx = order.indexOf(step);
  return (
    <div className="flex justify-center gap-2">
      {order.map((s, i) => (
        <span
          key={s}
          className={`h-1.5 w-12 rounded-full transition ${
            i <= idx ? "bg-brand-customer" : "bg-slate-200"
          }`}
        />
      ))}
    </div>
  );
}

function VehicleField({
  span,
  label,
  value,
  onChange,
  ...rest
}: {
  span: 1 | 2;
  label: string;
  value: string;
  onChange: (v: string) => void;
} & Omit<React.InputHTMLAttributes<HTMLInputElement>, "value" | "onChange">) {
  return (
    <label className={span === 2 ? "col-span-2 block" : "block"}>
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
