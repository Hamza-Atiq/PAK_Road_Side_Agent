// Source-of-truth strings. Keep keys snake_case. Add new keys here first;
// other locales fall back to en when a key is missing.

const en = {
  app_name: "RoadSide",
  tagline: "Help on the road, in minutes",

  // Role-toggle landing (apps/web)
  landing_customer_cta: "I need help",
  landing_provider_cta: "I provide help",
  landing_customer_subtitle: "Stuck on the road? Get help now.",
  landing_provider_subtitle: "Earn by helping drivers nearby.",

  // SOS flow
  sos_button: "Get help now",
  sos_confirm: "Press and hold to confirm",
  sos_picking_issue: "What happened?",

  // Trust strip
  trust_verified: "Verified provider",
  trust_tracked: "Live tracked",
  trust_no_charge: "No charge unless help arrives",

  // Status stepper
  status_reported: "Reported",
  status_analyzing: "Analyzing",
  status_assigned: "Provider assigned",
  status_en_route: "On the way",
  status_arrived: "Arrived",
  status_completed: "Done",
} as const;

export default en;
