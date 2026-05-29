// Design tokens — locked in V2_PLAN.md §3.2.
// Source of truth for ALL color/spacing/typography. Tailwind preset reads from here.
// Flutter side duplicates these by hand (Dart can't import TS).

export const colors = {
  brand: {
    customer: { primary: "#2473EB", dark: "#1E4DAF" }, // trust blue
    provider: { primary: "#16A34A", dark: "#15803D" }, // success green
    admin: { primary: "#7C3AED", dark: "#5B21B6" }, // violet
  },
  emergency: "#DC2626", // SOS button only
  warning: "#FF6600", // safety orange — EN_ROUTE, warnings
  success: "#16A34A",
  surface: { light: "#FFFFFF", dark: "#0B1220" },
  text: { primary: "#0B1220", inverse: "#F8FAFC", muted: "#64748B" },
} as const;

export const radius = {
  sm: "0.25rem",
  md: "0.5rem",
  lg: "0.75rem",
  xl: "1rem",
  pill: "9999px",
} as const;

export const fontFamily = {
  sans: ["Inter", "ui-sans-serif", "system-ui", "Segoe UI", "Roboto", "sans-serif"],
  display: ["Geist", "Inter Display", "Inter", "sans-serif"],
  mono: ["JetBrains Mono", "ui-monospace", "Menlo", "monospace"],
} as const;

export type ColorTokens = typeof colors;
