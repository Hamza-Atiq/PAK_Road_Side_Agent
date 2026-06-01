import { Navigate, Route, Routes } from "react-router-dom";
import { Landing } from "@/pages/Landing";
import { Login } from "@/pages/Login";
import { Register } from "@/pages/Register";
import { VerifyOTP } from "@/pages/VerifyOTP";
import { Onboarding } from "@/pages/Onboarding";
import { ReportIncident } from "@/pages/ReportIncident";
import { IncidentStatus } from "@/pages/IncidentStatus";
import { History } from "@/pages/History";
import { ProviderDashboard } from "@/pages/ProviderDashboard";
import { JobDetail } from "@/pages/JobDetail";
import { Layout } from "@/components/Layout";
import { ProtectedRoute } from "@/components/ProtectedRoute";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />

      {/* Customer */}
      <Route path="/customer/login" element={<Login role="customer" />} />
      <Route path="/customer/register" element={<Register role="customer" />} />
      <Route path="/customer/verify-otp" element={<VerifyOTP role="customer" />} />
      <Route
        path="/customer/onboarding"
        element={
          <ProtectedRoute role="customer">
            <Onboarding />
          </ProtectedRoute>
        }
      />
      <Route
        element={
          <ProtectedRoute role="customer">
            <Layout role="customer" />
          </ProtectedRoute>
        }
      >
        <Route path="/customer" element={<Navigate to="/customer/report" replace />} />
        <Route path="/customer/report" element={<ReportIncident />} />
        <Route path="/customer/incidents/:id" element={<IncidentStatus />} />
        <Route path="/customer/history" element={<History role="customer" />} />
      </Route>

      {/* Provider */}
      <Route path="/provider/login" element={<Login role="provider" />} />
      <Route path="/provider/register" element={<Register role="provider" />} />
      <Route path="/provider/verify-otp" element={<VerifyOTP role="provider" />} />
      <Route
        element={
          <ProtectedRoute role="provider">
            <Layout role="provider" />
          </ProtectedRoute>
        }
      >
        <Route path="/provider" element={<ProviderDashboard />} />
        <Route path="/provider/jobs/:id" element={<JobDetail />} />
        <Route path="/provider/history" element={<History role="provider" />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
