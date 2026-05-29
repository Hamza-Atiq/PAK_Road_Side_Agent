import { Navigate, useLocation } from "react-router-dom";
import { useAuthStore } from "@/store/auth";

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const isAuthed = useAuthStore((s) => s.isAuthed());
  const user = useAuthStore((s) => s.user);
  const location = useLocation();

  if (!isAuthed) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  // Hard guard: this app is for providers only
  if (user && user.role !== "provider") {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}
