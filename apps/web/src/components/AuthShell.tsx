import { Link } from "react-router-dom";
import { ReactNode } from "react";

interface Props {
  role: "customer" | "provider";
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}

export function AuthShell({ role, title, subtitle, children, footer }: Props) {
  const accent =
    role === "provider"
      ? "from-brand-provider/10 to-white"
      : "from-brand-customer/10 to-white";
  const badge =
    role === "provider" ? "bg-brand-provider text-white" : "bg-brand-customer text-white";
  return (
    <div className={`min-h-screen bg-gradient-to-b ${accent}`}>
      <header className="mx-auto flex max-w-2xl items-center justify-between px-6 pt-6">
        <Link to="/" className="flex items-center gap-2.5">
          <span
            aria-hidden
            className={`grid h-8 w-8 place-items-center rounded-lg ${badge} shadow-md`}
          >
            <svg viewBox="0 0 24 24" className="h-4 w-4">
              <path
                d="M12 2L2 20h20L12 2z"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinejoin="round"
                fill="#FF6600"
              />
            </svg>
          </span>
          <span className="text-lg font-extrabold tracking-tight text-slate-900">RoadSide</span>
        </Link>
        <span className="rounded-full bg-white/80 px-3 py-1 text-xs font-semibold uppercase tracking-wider text-slate-600 shadow-sm backdrop-blur">
          {role === "customer" ? "Customer" : "Provider"}
        </span>
      </header>

      <main className="mx-auto flex max-w-md flex-col px-6 py-10">
        <h1 className="text-3xl font-extrabold tracking-tight text-slate-900">{title}</h1>
        {subtitle && <p className="mt-2 text-slate-600">{subtitle}</p>}
        <div className="mt-8 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          {children}
        </div>
        {footer && <div className="mt-6 text-center text-sm text-slate-600">{footer}</div>}
      </main>
    </div>
  );
}
