import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { Login } from "@/pages/Login";
import { Register } from "@/pages/Register";
import { VerifyOTP } from "@/pages/VerifyOTP";
import { ReportIncident } from "@/pages/ReportIncident";
import { IncidentStatus } from "@/pages/IncidentStatus";
import { History } from "@/pages/History";

export default function App() {
  return (
    <Routes>
      {/* Public */}
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/verify-otp" element={<VerifyOTP />} />

      {/* Protected (customer area) */}
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<Navigate to="/report" replace />} />
        <Route path="/report" element={<ReportIncident />} />
        <Route path="/incidents/:id" element={<IncidentStatus />} />
        <Route path="/history" element={<History />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
