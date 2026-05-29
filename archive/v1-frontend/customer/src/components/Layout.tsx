import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/auth";
import { authApi } from "@/api/auth";

export function Layout() {
  const user = useAuthStore((s) => s.user);
  const clear = useAuthStore((s) => s.clear);
  const navigate = useNavigate();

  const handleLogout = async () => {
    try {
      await authApi.logout();
    } catch {
      // ignore — local clear is enough
    }
    clear();
    navigate("/login");
  };

  const navLinkClass = ({ isActive }: { isActive: boolean }) =>
    `px-3 py-2 rounded-md text-sm font-medium transition-colors ${
      isActive
        ? "bg-brand-600 text-white"
        : "text-slate-700 hover:bg-slate-100"
    }`;

  return (
    <div className="min-h-full flex flex-col">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-30">
        <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
          <div className="flex h-14 items-center justify-between gap-4">
            <Link to="/" className="flex items-center gap-2">
              <span className="inline-block h-7 w-7 rounded-md bg-brand-600 text-white grid place-items-center font-bold text-sm">
                R
              </span>
              <span className="font-semibold text-slate-900">RoadSide</span>
            </Link>

            <nav className="hidden sm:flex items-center gap-1">
              <NavLink to="/report" className={navLinkClass}>
                Report
              </NavLink>
              <NavLink to="/history" className={navLinkClass}>
                History
              </NavLink>
            </nav>

            <div className="flex items-center gap-2">
              {user && (
                <span className="text-sm text-slate-600 hidden sm:inline">
                  {user.name}
                </span>
              )}
              <button onClick={handleLogout} className="btn-secondary text-sm">
                Sign out
              </button>
            </div>
          </div>
          {/* Mobile nav */}
          <nav className="flex sm:hidden gap-1 pb-2">
            <NavLink to="/report" className={navLinkClass}>
              Report
            </NavLink>
            <NavLink to="/history" className={navLinkClass}>
              History
            </NavLink>
          </nav>
        </div>
      </header>

      <main className="flex-1 mx-auto w-full max-w-6xl px-4 sm:px-6 lg:px-8 py-6">
        <Outlet />
      </main>

      <footer className="text-center text-xs text-slate-500 py-4">
        RoadSide Agent · {new Date().getFullYear()}
      </footer>
    </div>
  );
}
