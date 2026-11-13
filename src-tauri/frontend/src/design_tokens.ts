/**
 * Electric Precision Design Tokens
 * Single source of truth for all colour, spacing, and semantic tokens.
 * Used by Tailwind config (build-time) and runtime components (theme-aware logic).
 */

/* ──────────────────────────────────────────────
   Core Electric Precision Palette
   ────────────────────────────────────────────── */
export const COLORS = {
  /* Accent / interactive */
  electricblue: "#38BDF8",
  electricblueHover: "#2563EB",
  electricbluePressed: "#1D4ED8",
  violet: "#8B9CFF",
  ice: "#E6EDF5",
  graphite: "#111827",

  /* Semantic state colours */
  healthy: "#34D399",
  warning: "#FBBF24",
  critical: "#FB7185",
  information: "#60A5FA",

  /* Interactive states */
  accent: "#60A5FA",
  accentHover: "#93C5FD",
  accentPressed: "#3B82F6",
  onAccent: "#0B1220", // graphite – for text on electricblue

  destructive: "#DC2626",
  destructiveHover: "#B91C1C",
  success: "#34D399",

  /* Selection */
  selectedBg: "#A5F3FC",
  selectedText: "#1E293B",

  /* Chart roles */
  chartCpu: "#38BDF8",
  chartMemory: "#8B9CFF",
  chartStorage: "#FBBF24",
  chartBattery: "#34D399",
  chartNetwork: "#60A5FA",
} as const;

/* ──────────────────────────────────────────────
   Light / Dark surface tokens
   ────────────────────────────────────────────── */
export const COLORS_LIGHT = {
  background: COLORS.ice, // #E6EDF5
  surface: "#FFFFFF",
  surfaceAlt: "#F8FAFC",
  surfaceElevated: "#F1F5F9",
  border: "#E2E8F0",
  borderStrong: "#CBD5E1",
  textPrimary: "#0F172A",
  textSecondary: "#55657C",
  sidebarBg: "#0B1220",
  sidebarText: "#E6EDF5",
  sidebarHover: "#16213A",
} as const;

export const COLORS_DARK = {
  background: "#0B1220",
  slate: "#202C3B",
  surface: "#111A2C",
  surfaceAlt: "#0E1726",
  surfaceElevated: "#16213A",
  border: "#24324A",
  borderStrong: "#334155",
  textPrimary: "#E6EDF7",
  textSecondary: "#94A3B8",
  sidebarBg: "#070D18",
  sidebarText: "#CBD5E1",
  sidebarHover: "#16213A",
} as const;

/* ──────────────────────────────────────────────
   Tailwind colour keys (must match tailwind.config.js)
   ────────────────────────────────────────────── */
export const TAILWIND_COLOR_KEYS = {
  /* Palette */
  electricblue: "electricblue",
  electricblueHover: "electricblueHover",
  electricbluePressed: "electricbluePressed",
  violet: "violet",
  ice: "ice",
  graphite: "graphite",

  /* Semantic */
  healthy: "healthy",
  warning: "warning",
  critical: "critical",
  criticalState: "criticalState", // alias
  information: "information",

  /* Light surfaces */
  lightBackground: "lightBackground",
  lightSurface: "lightSurface",
  lightSurfaceAlt: "lightSurfaceAlt",
  lightSurfaceElevated: "lightSurfaceElevated",
  lightBorder: "lightBorder",
  lightBorderStrong: "lightBorderStrong",
  lightTextPrimary: "lightTextPrimary",
  lightTextSecondary: "lightTextSecondary",
  lightSidebarBg: "lightSidebarBg",
  lightSidebarText: "lightSidebarText",
  lightSidebarHover: "lightSidebarHover",

  /* Dark surfaces */
  darkBackground: "darkBackground",
  darkSlate: "darkSlate",
  darkSurface: "darkSurface",
  darkSurfaceAlt: "darkSurfaceAlt",
  darkSurfaceElevated: "darkSurfaceElevated",
  darkBorder: "darkBorder",
  darkBorderStrong: "darkBorderStrong",
  darkTextPrimary: "darkTextPrimary",
  darkTextSecondary: "darkTextSecondary",
  darkSidebarBg: "darkSidebarBg",
  darkSidebarText: "darkSidebarText",
  darkSidebarHover: "darkSidebarHover",

  /* Interactive */
  accent: "accent",
  accentHover: "accentHover",
  accentPressed: "accentPressed",
  onAccent: "onAccent",
  destructive: "destructive",
  destructiveHover: "destructiveHover",
  success: "success",

  /* Selection */
  selectedBg: "selectedBg",
  selectedText: "selectedText",

  /* Charts */
  chartCpu: "chartCpu",
  chartMemory: "chartMemory",
  chartStorage: "chartStorage",
  chartBattery: "chartBattery",
  chartNetwork: "chartNetwork",

  /* Panels */
  panelBorder: "panelBorder",
  panelBorderLight: "panelBorderLight",
} as const;

/* ──────────────────────────────────────────────
   Helper: resolve theme-aware surface classes
   ────────────────────────────────────────────── */
export type ResolvedTheme = "light" | "dark";

export function getSurfaceClasses(resolvedTheme: ResolvedTheme): {
  background: string;
  surface: string;
  surfaceAlt: string;
  surfaceElevated: string;
  border: string;
  textPrimary: string;
  textSecondary: string;
  sidebarBg: string;
  sidebarText: string;
  sidebarHover: string;
} {
  if (resolvedTheme === "light") {
    return {
      background: "bg-lightBackground",
      surface: "bg-lightSurface",
      surfaceAlt: "bg-lightSurfaceAlt",
      surfaceElevated: "bg-lightSurfaceElevated",
      border: "border-lightBorder",
      textPrimary: "text-lightTextPrimary",
      textSecondary: "text-lightTextSecondary",
      sidebarBg: "bg-lightSidebarBg",
      sidebarText: "text-lightSidebarText",
      sidebarHover: "hover:bg-lightSidebarHover",
    };
  }
  return {
    background: "bg-darkBackground",
    surface: "bg-darkSurface",
    surfaceAlt: "bg-darkSurfaceAlt",
    surfaceElevated: "bg-darkSurfaceElevated",
    border: "border-darkBorder",
    textPrimary: "text-darkTextPrimary",
    textSecondary: "text-darkTextSecondary",
    sidebarBg: "bg-darkSidebarBg",
    sidebarText: "text-darkSidebarText",
    sidebarHover: "hover:bg-darkSidebarHover",
  };
}

/* ──────────────────────────────────────────────
   Semantic colour class helpers
   ────────────────────────────────────────────── */
export type SemanticLevel = "healthy" | "warning" | "critical" | "info";

export function getSemanticClasses(level: SemanticLevel): {
  bg: string;
  border: string;
  text: string;
  bgSubtle: string; // /20 opacity
} {
  const base = level === "info" ? "information" : level;
  return {
    bg: `bg-${base}`,
    border: `border-${base}`,
    text: `text-${base}`,
    bgSubtle: `bg-${base}/20`,
  };
}

/* ──────────────────────────────────────────────
   Progress bar colour helpers
   ────────────────────────────────────────────── */
export type ProgressLevel = "normal" | "warning" | "critical" | "accent";

export function getProgressClasses(level: ProgressLevel): string {
  switch (level) {
    case "critical":
      return "bg-critical";
    case "warning":
      return "bg-warning";
    case "accent":
      return "bg-accent";
    default:
      return "bg-healthy";
  }
}

/* ──────────────────────────────────────────────
   Spacing / radius tokens (mirroring Tailwind scale)
   ────────────────────────────────────────────── */
export const SPACING = {
  xs: "0.25rem",
  sm: "0.5rem",
  md: "1rem",
  lg: "1.5rem",
  xl: "2rem",
  "2xl": "3rem",
} as const;

export const RADIUS = {
  sm: "0.25rem",
  md: "0.375rem",
  lg: "0.5rem",
  xl: "0.75rem",
  "2xl": "1rem",
  full: "9999px",
} as const;

/* ──────────────────────────────────────────────
   Typography tokens
   ────────────────────────────────────────────── */
export const TYPOGRAPHY = {
  fontSans: '"Geist Sans", "Segoe UI", system-ui, sans-serif',
  fontMono: '"Geist Mono", monospace',
  sizes: {
    xs: "0.75rem",
    sm: "0.875rem",
    base: "1rem",
    lg: "1.125rem",
    xl: "1.25rem",
    "2xl": "1.5rem",
    "3xl": "1.875rem",
    "4xl": "2.25rem",
  },
  weights: {
    normal: "400",
    medium: "500",
    semibold: "600",
    bold: "700",
  },
} as const;

export default {
  COLORS,
  COLORS_LIGHT,
  COLORS_DARK,
  TAILWIND_COLOR_KEYS,
  getSurfaceClasses,
  getSemanticClasses,
  getProgressClasses,
  SPACING,
  RADIUS,
  TYPOGRAPHY,
};