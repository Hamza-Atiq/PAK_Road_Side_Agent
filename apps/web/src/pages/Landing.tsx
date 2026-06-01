import { Link } from "react-router-dom";

export function Landing() {
  return (
    <div className="relative min-h-screen overflow-hidden bg-gradient-to-b from-white via-slate-50 to-slate-100">
      <GridBackdrop />
      <header className="relative z-10 mx-auto flex max-w-6xl items-center justify-between px-6 pt-6">
        <Wordmark />
        <nav className="hidden gap-8 text-sm font-medium text-slate-600 sm:flex">
          <a className="hover:text-slate-900" href="#how">How it works</a>
          <a className="hover:text-slate-900" href="#trust">Why us</a>
          <a className="hover:text-slate-900" href="#providers">For providers</a>
        </nav>
      </header>

      <main className="relative z-10 mx-auto flex max-w-6xl flex-col items-center px-6 pb-24 pt-16 text-center sm:pt-24">
        <span className="rounded-full border border-slate-200 bg-white/70 px-4 py-1.5 text-xs font-semibold uppercase tracking-wider text-slate-600 shadow-sm backdrop-blur">
          AI-dispatched roadside assistance
        </span>

        <h1 className="mt-6 max-w-3xl text-4xl font-extrabold tracking-tight text-slate-900 sm:text-5xl md:text-6xl">
          Help on the road, <span className="text-brand-customer">in minutes</span>.
        </h1>

        <p className="mt-5 max-w-2xl text-lg text-slate-600">
          Stranded? RoadSide&apos;s AI agents diagnose the problem, dispatch the closest verified
          provider, and keep you informed every minute &mdash; in any country.
        </p>

        <div className="mt-10 grid w-full max-w-2xl grid-cols-1 gap-4 sm:grid-cols-2">
          <Link to="/customer" className="btn-primary group">
            <span aria-hidden className="text-2xl transition-transform group-hover:-translate-y-0.5">
              🆘
            </span>
            I need help
          </Link>
          <Link to="/provider" className="btn-secondary group">
            <span aria-hidden className="text-2xl transition-transform group-hover:-translate-y-0.5">
              🔧
            </span>
            I provide help
          </Link>
        </div>

        <p className="mt-4 text-sm text-slate-500">
          No app required to start. Sign in with Apple, Google, Facebook or phone.
        </p>

        <TrustStrip />

        <HowItWorks />
      </main>

      <footer className="relative z-10 mx-auto max-w-6xl px-6 pb-10 text-center text-xs text-slate-500">
        &copy; {new Date().getFullYear()} RoadSide. Available worldwide.
      </footer>
    </div>
  );
}

function Wordmark() {
  return (
    <Link to="/" className="flex items-center gap-2.5">
      <span
        aria-hidden
        className="grid h-9 w-9 place-items-center rounded-xl bg-brand-customer text-white shadow-md shadow-brand-customer/30"
      >
        <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5">
          <path
            d="M12 2L2 20h20L12 2z"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinejoin="round"
            fill="#FF6600"
          />
          <circle cx="12" cy="15" r="1.5" fill="currentColor" />
        </svg>
      </span>
      <span className="text-xl font-extrabold tracking-tight text-slate-900">RoadSide</span>
    </Link>
  );
}

function TrustStrip() {
  const items = [
    { icon: "🛡️", label: "Verified providers", sub: "License + insurance checked" },
    { icon: "📍", label: "Live tracking", sub: "Share link with family" },
    { icon: "💳", label: "No charge unless help arrives", sub: "Cancel anytime, free" },
  ];
  return (
    <div
      id="trust"
      className="mt-16 grid w-full max-w-4xl grid-cols-1 gap-4 sm:grid-cols-3"
    >
      {items.map((it) => (
        <div
          key={it.label}
          className="flex items-start gap-3 rounded-2xl border border-slate-200 bg-white/80 px-5 py-4 text-left shadow-sm backdrop-blur"
        >
          <span aria-hidden className="text-2xl leading-none">{it.icon}</span>
          <div>
            <div className="font-semibold text-slate-900">{it.label}</div>
            <div className="text-xs text-slate-500">{it.sub}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

function HowItWorks() {
  const steps = [
    {
      n: "01",
      title: "Tell us what happened",
      desc: "Tap an issue, snap a photo, or speak a quick voice note. 30 seconds.",
    },
    {
      n: "02",
      title: "AI diagnoses + dispatches",
      desc: "Our agents read your input, find the closest verified provider, and confirm price upfront.",
    },
    {
      n: "03",
      title: "Live track until help arrives",
      desc: "Watch them approach on the map. Share the link with family for peace of mind.",
    },
  ];
  return (
    <section id="how" className="mt-20 grid w-full max-w-4xl gap-4 sm:grid-cols-3">
      {steps.map((s) => (
        <div
          key={s.n}
          className="rounded-2xl border border-slate-200 bg-white p-6 text-left shadow-sm"
        >
          <div className="font-mono text-xs font-bold text-brand-customer">{s.n}</div>
          <div className="mt-2 text-lg font-semibold text-slate-900">{s.title}</div>
          <div className="mt-1 text-sm text-slate-600">{s.desc}</div>
        </div>
      ))}
    </section>
  );
}

function GridBackdrop() {
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute inset-0 [background-image:linear-gradient(to_right,rgba(36,115,235,0.06)_1px,transparent_1px),linear-gradient(to_bottom,rgba(36,115,235,0.06)_1px,transparent_1px)] [background-size:32px_32px] [mask-image:radial-gradient(ellipse_at_top,black_30%,transparent_70%)]"
    />
  );
}
