/** @type {import('tailwindcss').Config} */
// Admin keeps its violet `brand-{50..900}` scale (Phase 15 styles depend on it).
// We additionally pull in the universal status colors from @roadside/ui so the
// whole monorepo agrees on emergency/warning/success palettes.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  "#f5f3ff",
          100: "#ede9fe",
          200: "#ddd6fe",
          300: "#c4b5fd",
          400: "#a78bfa",
          500: "#8b5cf6",
          600: "#7c3aed",
          700: "#6d28d9",
          800: "#5b21b6",
          900: "#4c1d95",
        },
        emergency: "#DC2626",
        warning: "#FF6600",
        success: "#16A34A",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        display: ["Geist", "Inter Display", "Inter", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};
