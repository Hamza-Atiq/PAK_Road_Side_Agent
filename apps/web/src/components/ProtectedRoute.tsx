import { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuthStore } from "@/store/auth";

export function ProtectedRoute({
  role,
  children,
}: {
  role: "customer" | "provider" | "admin";
  children: ReactNode;
}) {
  const { accessToken, user } = useAuthStore();
  const loc = useLocation();

  if (!accessToken || !user) {
    const loginPath = role === "provider" ? "/provider/login" : "/customer/login";
    return <Navigate to={loginPath} replace state={{ from: loc.pathname }} />;
  }

  if (user.role !== role) {
    // Wrong role — bounce to the correct dashboard.
    return <Navigate to={user.role === "provider" ? "/provider" : "/customer/report"} replace />;
  }

  return <>{children}</>;
}
