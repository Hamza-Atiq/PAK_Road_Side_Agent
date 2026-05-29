// Shared TS types. Mirrors backend enums where they're stable.
// API request/response types live in @roadside/api-client (generated).

export type UserRole = "customer" | "provider" | "admin";

export type IncidentStatus =
  | "REPORTED"
  | "ANALYZING"
  | "ASSIGNED"
  | "EN_ROUTE"
  | "ARRIVED"
  | "COMPLETED"
  | "CLOSED"
  | "NO_PROVIDER"
  | "ESCALATED";

export type ServiceType =
  | "tow"
  | "battery"
  | "tire"
  | "fuel"
  | "lockout"
  | "winch"
  | "other";

export type PricingMode = "PER_USE" | "MEMBER";
