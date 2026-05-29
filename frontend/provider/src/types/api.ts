export type UserRole = "customer" | "provider" | "admin";

export type IncidentStatus =
  | "REPORTED" | "ANALYZING" | "ASSIGNED" | "NO_PROVIDER" | "ESCALATED"
  | "EN_ROUTE" | "ARRIVED" | "COMPLETED" | "CLOSED";

export type IncidentSeverity = "low" | "medium" | "high" | "critical" | "unknown";

export type ServiceType =
  | "mechanic" | "tow_truck" | "tire" | "battery" | "fuel" | "locksmith" | "other";

export interface User {
  id: string;
  phone: string;
  name: string;
  email: string | null;
  role: UserRole;
  is_active: boolean;
  is_phone_verified: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface ProviderProfile {
  id: string;
  service_type: string;
  vehicle_info: string | null;
  is_available: boolean;
  is_approved: boolean;
  total_jobs: number;
  last_ping: string | null;
}

export interface AIDiagnosis {
  issue_type: string;
  severity: IncidentSeverity;
  service_needed: ServiceType;
  confidence: number;
  details?: string | null;
}

export interface Incident {
  id: string;
  customer_id: string;
  provider_id: string | null;
  status: IncidentStatus;
  lat: number;
  lng: number;
  address: string | null;
  description: string | null;
  image_url: string | null;
  voice_url: string | null;
  ai_diagnosis: AIDiagnosis | null;
  eta_minutes: number | null;
  guardrail_flagged: boolean;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface IncidentBrief {
  id: string;
  status: IncidentStatus;
  lat: number;
  lng: number;
  provider_id: string | null;
  eta_minutes: number | null;
  created_at: string;
  updated_at: string;
}

export interface IncidentListResponse {
  total: number;
  limit: number;
  offset: number;
  items: IncidentBrief[];
}

export interface WSEvent {
  event: string;
  incident_id?: string | null;
  agent?: string | null;
  timestamp?: string;
  data?: Record<string, unknown>;
  scope?: string;
}
