// Tailwind preset — apps/web and apps/admin extend from this so brand tokens
// stay in sync. To use:
//   import preset from "@roadside/ui/tailwind-preset";
//   export default { presets: [preset], content: [...] };
module.exports = {
  theme: {
    extend: {
      colors: {
        brand: {
          customer: { DEFAULT: "#2473EB", dark: "#1E4DAF" },
          provider: { DEFAULT: "#16A34A", dark: "#15803D" },
          admin: { DEFAULT: "#7C3AED", dark: "#5B21B6" },
        },
        emergency: "#DC2626",
        warning: "#FF6600",
        success: "#16A34A",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "Segoe UI", "Roboto", "sans-serif"],
        display: ["Geist", "Inter Display", "Inter", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "Menlo", "monospace"],
      },
    },
  },
};
