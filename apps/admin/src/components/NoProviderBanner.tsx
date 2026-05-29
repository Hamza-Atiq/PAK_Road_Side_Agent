import { Link } from "react-router-dom";
import { useNoProviderAlert } from "@/hooks/useNoProviderAlert";

/**
 * Sticky alert shown on every page when one or more incidents are stuck in
 * NO_PROVIDER state. Polling lives in `useNoProviderAlert` so the banner
 * stays accurate independent of which page is currently mounted.
 */
export function NoProviderBanner() {
  const { count } = useNoProviderAlert();
  if (count === 0) return null;

  return (
    <div className="bg-rose-600 text-white">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-2 flex items-center justify-between gap-3 text-sm">
        <div className="flex items-center gap-2">
          <span aria-hidden>⚠️</span>
          <span>
            <span className="font-semibold">{count}</span>{" "}
            incident{count === 1 ? "" : "s"} stuck in NO_PROVIDER — manual reassignment needed.
          </span>
        </div>
        <Link
          to="/incidents?status=NO_PROVIDER"
          className="font-semibold underline underline-offset-2 hover:opacity-90"
        >
          Review →
        </Link>
      </div>
    </div>
  );
}
