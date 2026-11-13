/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        /* Electric Precision palette */
        electricblue: "#38BDF8",
        electricblueHover: "#2563EB",
        electricbluePressed: "#1D4ED8",
        violet: "#8B9CFF",
        ice: "#E6EDF5",
        graphite: "#111827",

        /* Semantic colours – must communicate real states */
        healthy: "#34D399",
        warning: "#FBBF24",
        critical: "#FB7185",
        criticalState: "#FB7185", // alias for backward compatibility
        information: "#60A5FA",

        /* Base neutrals – light */
        lightBackground: "#F5F7FA",
        lightSurface: "#FFFFFF",
        lightSurfaceAlt: "#F8FAFC",
        lightSurfaceElevated: "#F1F5F9",
        lightBorder: "#E2E8F0",
        lightBorderStrong: "#CBD5E1",
        lightTextPrimary: "#0F172A",
        lightTextSecondary: "#55657C",
        lightSidebarBg: "#0B1220",
        lightSidebarText: "#E6EDF5",
        lightSidebarHover: "#16213A",

        /* Base neutrals – dark */
        darkBackground: "#0B1220",
        darkSlate: "#202C3B",
        darkSurface: "#111A2C",
        darkSurfaceAlt: "#0E1726",
        darkSurfaceElevated: "#16213A",
        darkBorder: "#24324A",
        darkBorderStrong: "#334155",
        darkTextPrimary: "#E6EDF7",
        darkTextSecondary: "#94A3B8",
        darkSidebarBg: "#070D18",
        darkSidebarText: "#CBD5E1",
        darkSidebarHover: "#16213A",

        /* Interactive states */
        accent: "#60A5FA",
        accentHover: "#93C5FD",
        accentPressed: "#3B82F6",
        onAccent: "#0B1220",

        destructive: "#DC2626",
        destructiveHover: "#B91C1C",

        success: "#34D399",

        /* selected */
        selectedBg: "#A5F3FC",
        selectedText: "#1E293B",

        /* Chart roles */
        chartCpu: "#38BDF8",
        chartMemory: "#8B9CFF",
        chartStorage: "#FBBF24",
        chartBattery: "#34D399",
        chartNetwork: "#60A5FA",

        /* Panel border colors */
        panelBorder: "#24324A",
        panelBorderLight: "#6B7280",
      },
      fontFamily: {
        sans: ['"Geist Sans"', '"Segoe UI"', "system-ui", "sans-serif"],
        mono: ['"Geist Mono"', "monospace"],
      },
    },
  },
  plugins: [
    require("tailwindcss-animate"),
    function ({ addComponents, addUtilities }) {
      addComponents({
        /* Shared components will be added here */
      });

      addUtilities({
        /* Shared utilities will be added here */
      });
    },
  ],
};