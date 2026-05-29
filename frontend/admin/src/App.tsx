import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { Login } from "@/pages/Login";
import { LiveMap } from "@/pages/LiveMap";
import { Incidents } from "@/pages/Incidents";
import { Providers } from "@/pages/Providers";
import { Metrics } from "@/pages/Metrics";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<Navigate to="/live" replace />} />
        <Route path="/live" element={<LiveMap />} />
        <Route path="/incidents" element={<Incidents />} />
        <Route path="/providers" element={<Providers />} />
        <Route path="/metrics" element={<Metrics />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
