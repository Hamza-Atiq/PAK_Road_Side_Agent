/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  "#eff8ff",
          100: "#dbedfe",
          200: "#bfe0fe",
          300: "#93cdfd",
          400: "#60b1fa",
          500: "#3a91f6",
          600: "#2473eb",
          700: "#1d5dd8",
          800: "#1e4daf",
          900: "#1e438a",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};
