import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/auth";
import { authApi } from "@/lib/api";

interface Props {
  role: "customer" | "provider";
}

export function Layout({ role }: Props) {
  const navigate = useNavigate();
  const { user, clear } = useAuthStore();

  const logout = async () => {
    try {
      await authApi.logout();
    } catch {
      /* ignore */
    }
    clear();
    navigate("/", { replace: true });
  };

  const nav =
    role === "customer"
      ? [
          { to: "/customer/report", label: "Get help" },
          { to: "/customer/history", label: "History" },
        ]
      : [
          { to: "/provider", label: "Dashboard", end: true },
          { to: "/provider/history", label: "History" },
        ];

  const badge =
    role === "provider"
      ? "bg-brand-provider/10 text-brand-provider-dark"
      : "bg-brand-customer/10 text-brand-customer-dark";

  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <Link to="/" className="flex items-center gap-2.5">
            <span
              aria-hidden
              className={
                role === "provider"
                  ? "grid h-8 w-8 place-items-center rounded-lg bg-brand-provider text-white shadow-md"
                  : "grid h-8 w-8 place-items-center rounded-lg bg-brand-customer text-white shadow-md"
              }
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
            <span className={`hidden rounded-full px-2 py-0.5 text-xs font-semibold sm:inline ${badge}`}>
              {role}
            </span>
          </Link>

          <nav className="hidden gap-1 sm:flex">
            {nav.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={"end" in item ? item.end : undefined}
                className={({ isActive }) =>
                  `rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                    isActive
                      ? "bg-slate-100 text-slate-900"
                      : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="flex items-center gap-3">
            <span className="hidden text-sm text-slate-600 sm:inline">
              {user?.name ?? user?.phone}
            </span>
            <button
              onClick={logout}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Sign out
            </button>
          </div>
        </div>

        <nav className="flex gap-1 border-t border-slate-100 px-4 py-2 sm:hidden">
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={"end" in item ? item.end : undefined}
              className={({ isActive }) =>
                `flex-1 rounded-lg px-3 py-1.5 text-center text-sm font-medium transition ${
                  isActive
                    ? "bg-slate-100 text-slate-900"
                    : "text-slate-600 hover:bg-slate-50"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6">
        <Outlet />
      </main>

      <footer className="border-t border-slate-200 bg-white py-4 text-center text-xs text-slate-500">
        RoadSide &middot; {new Date().getFullYear()} &middot; help@roadsideagent.com
      </footer>
    </div>
  );
}
