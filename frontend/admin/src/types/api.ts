// Shared types — kept in sync with backend pydantic schemas in
// backend/app/schemas/{admin,incident,provider}.py

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

export interface ProviderListItem {
  id: string;
  name: string;
  phone: string;
  service_type: string;
  is_available: boolean;
  is_approved: boolean;
  total_jobs: number;
  last_ping: string | null;
}

export interface ProviderListResponse {
  total: number;
  items: ProviderListItem[];
}

// ---------- Admin dashboard ----------

export interface IncidentCountsByStatus {
  REPORTED: number;
  ANALYZING: number;
  ASSIGNED: number;
  NO_PROVIDER: number;
  ESCALATED: number;
  EN_ROUTE: number;
  ARRIVED: number;
  COMPLETED: number;
  CLOSED: number;
}

export interface ProviderCounts {
  total_approved: number;
  available_now: number;
  online_pingers: number;
  on_active_job: number;
}

export interface MessagingStats {
  total_24h: number;
  delivered_24h: number;
  failed_24h: number;
  delivery_rate: number;
}

export interface DashboardResponse {
  incidents_by_status: IncidentCountsByStatus;
  incident_counts_24h: number;
  providers: ProviderCounts;
  messaging: MessagingStats;
  open_incidents_count: number;
  avg_eta_minutes_24h: number | null;
  generated_at: string;
}

// ---------- Admin actions ----------

export interface NotifyRequest {
  to_phone: string;
  body: string;
  channel?: "sms" | "whatsapp";
  incident_id?: string | null;
}

export interface NotifyResponse {
  message_id: string;
  twilio_sid: string | null;
  delivery_status: string;
}

export interface ReassignRequest {
  new_provider_id?: string | null;
  reason?: string | null;
}

export interface ReassignResponse {
  incident_id: string;
  new_provider_id: string | null;
  new_provider_name: string | null;
  status: string;
  notes: string;
}

export interface AdminQueryRequest {
  query: string;
}

export interface AdminQueryResponse {
  intent: string;
  summary: string;
  data: Record<string, unknown> | null;
  actioned: boolean;
}

// ---------- WebSocket envelope ----------

export interface WSEvent {
  event: string;
  incident_id?: string | null;
  agent?: string | null;
  timestamp?: string;
  data?: Record<string, unknown>;
  scope?: string;
}
