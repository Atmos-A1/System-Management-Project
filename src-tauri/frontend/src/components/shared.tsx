import { FC, ReactNode, useEffect, useState, Component, ErrorInfo } from "react";
import { useTheme } from "../context/ThemeContext";
import { getSurfaceClasses, getSemanticClasses, getProgressClasses, type ResolvedTheme, type ProgressLevel } from "../design_tokens";

/* ──────────────────────────────────────────────
   PageScaffold – standard shell layout with header
   ────────────────────────────────────────────── */
export const PageScaffold: FC<{
  title: string;
  subtitle?: string;
  children: ReactNode;
  margins?: number;
  spacing?: number;
}> = ({ title, subtitle, children }) => {
  const { resolvedTheme } = useTheme();
  const surfaces = getSurfaceClasses(resolvedTheme);
  const isDark = resolvedTheme === "dark";

  return (
    <div className={`flex min-h-screen flex-col ${surfaces.background}`}>
      <header className={`border-b ${surfaces.border} ${isDark ? "bg-darkSurface/50" : "bg-lightSurface/50"}`}>
        <div className="flex items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <h1 className={`text-xl font-semibold tracking-tight ${surfaces.textPrimary}`}>{title}</h1>
            {subtitle && <p className={`text-sm ${surfaces.textSecondary}`}>{subtitle}</p>}
          </div>
          <div className="flex items-center gap-2">
            {/* Theme toggle is now in sidebar */}
          </div>
        </div>
      </header>
      <main className="flex-1 p-6 overflow-y-auto">{children}</main>
    </div>
  );
};

/* ──────────────────────────────────────────────
   Toolbar – consistent bar with action buttons
   ────────────────────────────────────────────── */
export const Toolbar: FC<{
  children: ReactNode;
  alignRight?: boolean;
}> = ({ children, alignRight = false }) => {
  const { resolvedTheme } = useTheme();
  const surfaces = getSurfaceClasses(resolvedTheme);
  const className = alignRight ? "justify-between flex items-center" : "flex items-center";
  return (
    <div className={`flex ${className} border-b pb-3 mb-4 ${surfaces.border}`}>
      {children}
    </div>
  );
};

/* ──────────────────────────────────────────────
   Badge – labeled status with semantic colour coding
   ────────────────────────────────────────────── */
export const Badge: FC<{
  text: string;
  status: "info" | "success" | "warning" | "critical";
  variant?: "pill" | "flat";
  className?: string;
}> = ({ text, status, variant = "pill", className = "" }) => {
  const semanticMap: Record<string, "healthy" | "warning" | "critical" | "info"> = {
    info: "info",
    success: "healthy",
    warning: "warning",
    critical: "critical",
  };
  const classes = getSemanticClasses(semanticMap[status]);
  const variantStyles = variant === "pill" ? "rounded-full" : "rounded-md";
  return (
    <span
      className={`inline-flex items-center ${variantStyles} ${classes.bgSubtle} ${classes.border} text-xs font-semibold ${classes.text} ${className}`}
    >
      {text}
    </span>
  );
};

/* ──────────────────────────────────────────────
   MetricCard – prominent system metric with progress
   ────────────────────────────────────────────── */
export const MetricCard: FC<{
  title: string;
  subtitle: string;
  value: string;
  detail: string;
  showProgress?: boolean;
  progressLevel?: ProgressLevel;
  compact?: boolean;
}> = ({
  title,
  subtitle,
  value,
  detail,
  showProgress = true,
  progressLevel = "normal",
  compact = false,
}) => {
  const { resolvedTheme } = useTheme();
  const surfaces = getSurfaceClasses(resolvedTheme);
  const progressClass = showProgress
    ? `h-2 rounded-full ${getProgressClasses(progressLevel)}`
    : "h-0";

  return (
    <div
      className={`rounded-xl border ${surfaces.border} ${surfaces.surface} p-6 shadow-sm ${compact ? "p-4" : "p-6"}`}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <svg className={`w-5 h-5 ${surfaces.textSecondary}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
          <h3 className={`text-sm font-semibold ${surfaces.textPrimary}`}>{title}</h3>
        </div>
        <p className={`text-xs ${surfaces.textSecondary}`}>{subtitle}</p>
      </div>
      <div className="mt-2">
        <p className={`text-2xl font-bold tracking-tight ${surfaces.textPrimary}`}>{value}</p>
      </div>
      <p className={`mt-2 text-sm ${surfaces.textSecondary}`}>{detail}</p>
      {showProgress && <div className={`mt-3 ${progressClass}`} />}
    </div>
  );
};

/* ──────────────────────────────────────────────
   SectionCard – styled card for grouping content
   ────────────────────────────────────────────── */
export const SectionCard: FC<{
  title: string;
  subtitle?: string;
  children: ReactNode;
  className?: string;
}> = ({ title, subtitle, children, className = "" }) => {
  const { resolvedTheme } = useTheme();
  const surfaces = getSurfaceClasses(resolvedTheme);
  return (
    <div className={`rounded-lg border ${surfaces.border} ${surfaces.surface} p-6 shadow-sm ${className}`}>
      <div className="flex items-start justify-between mb-4">
        <h3 className={`text-lg font-semibold ${surfaces.textPrimary}`}>{title}</h3>
        {subtitle && <p className={`text-xs ${surfaces.textSecondary}`}>{subtitle}</p>}
      </div>
      <div>{children}</div>
    </div>
  );
};

/* ──────────────────────────────────────────────
   FilterBar – search and filter controls
   ────────────────────────────────────────────── */
export const FilterBar: FC<{
  placeholder?: string;
  onSearch?: (text: string) => void;
  onFilterChange?: (value: string) => void;
}> = ({ placeholder = "Search…", onSearch, onFilterChange }) => {
  const { resolvedTheme } = useTheme();
  const surfaces = getSurfaceClasses(resolvedTheme);
  return (
    <div
      className={`flex items-center gap-2 px-3 py-2 rounded-lg border ${surfaces.border} ${surfaces.surfaceAlt} focus-within:ring-2 focus-within:ring-electricblue`}
    >
      <input
        type="text"
        placeholder={placeholder}
        className={`flex-1 bg-transparent outline-none ${surfaces.textPrimary} placeholder-${surfaces.textSecondary}`}
        onChange={(e) => onSearch && onSearch(e.target.value)}
      />
      {onFilterChange && (
        <select
          className={`bg-transparent outline-none ${surfaces.textPrimary} rounded-md px-2 py-1 border ${surfaces.border}`}
          onChange={(e) => onFilterChange(e.target.value)}
        >
          <option value="">All</option>
          <option value="running">Running</option>
          <option value="sleeping">Sleeping</option>
          <option value="stopped">Stopped</option>
        </select>
      )}
    </div>
  );
};

/* ──────────────────────────────────────────────
   EmptyState – displayed when no data available
   ────────────────────────────────────────────── */
export const EmptyState: FC<{
  icon: ReactNode;
  title: string;
  description: string;
  actionLabel?: string;
  actionOnClick?: () => void;
}> = ({ icon, title, description, actionLabel, actionOnClick }) => {
  const { resolvedTheme } = useTheme();
  const surfaces = getSurfaceClasses(resolvedTheme);
  return (
    <div className="text-center py-12">
      <div className={`mx-auto text-6xl ${surfaces.textSecondary}`}>{icon}</div>
      <h3 className={`text-lg font-medium ${surfaces.textPrimary} mt-4`}>{title}</h3>
      <p className={`text-sm ${surfaces.textSecondary} mt-2`}>{description}</p>
      {actionLabel && actionOnClick && (
        <button
          className="mt-4 rounded-md bg-electricblue text-onAccent hover:bg-electricblueHover transition-colors px-4 py-2 text-sm font-medium"
          onClick={actionOnClick}
        >
          {actionLabel}
        </button>
      )}
    </div>
  );
};

/* ──────────────────────────────────────────────
   LoadingState – displayed while data is fetching
   ────────────────────────────────────────────── */
export const LoadingState: FC<{
  size?: "sm" | "md" | "lg";
}> = ({ size = "md" }) => {
  const { resolvedTheme } = useTheme();
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);
  const surfaces = getSurfaceClasses(resolvedTheme);

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    setPrefersReducedMotion(media.matches);
    const handler = () => setPrefersReducedMotion(media.matches);
    media.addEventListener("change", handler);
    return () => media.removeEventListener("change", handler);
  }, []);

  const sizeMap = { sm: "h-8 w-8", md: "h-12 w-12", lg: "h-16 w-16" };
  const spinClass = prefersReducedMotion ? "" : "animate-spin";

  return (
    <div className={`flex flex-col items-center justify-center py-8 ${sizeMap[size]}`}>
      <div className={`flex h-8 w-8 rounded-full ring-4 ${surfaces.border} ${surfaces.surfaceAlt}`}>
        <div className={`h-8 w-8 rounded-full ring-4 ring-electricblue ring-opacity-75 ${spinClass}`} />
      </div>
      <p className={`mt-2 text-sm ${surfaces.textSecondary}`}>Loading…</p>
    </div>
  );
};

/* ──────────────────────────────────────────────
   ErrorState – displayed when an error occurs
   ────────────────────────────────────────────── */
export const ErrorState: FC<{
  title: string;
  description: string;
  retryLabel?: string;
  retryOnClick?: () => void;
}> = ({ title, description, retryLabel, retryOnClick }) => {
  const { resolvedTheme } = useTheme();
  const surfaces = getSurfaceClasses(resolvedTheme);
  const criticalClasses = getSemanticClasses("critical");

  return (
    <div className={`rounded-lg border ${criticalClasses.border} ${criticalClasses.bgSubtle} p-6 mb-6`}>
      <div className="flex">
        <div className="flex-shrink-0">
          <svg className={`w-5 h-5 ${criticalClasses.text}`} viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        </div>
        <div className="ml-3">
          <h4 className={`text-sm font-medium ${criticalClasses.text}`}>{title}</h4>
          <p className={`text-sm mt-1 ${surfaces.textSecondary}`}>{description}</p>
          {retryLabel && retryOnClick && (
            <button
              className="mt-3 rounded-md bg-electricblue text-onAccent hover:bg-electricblueHover transition-colors px-3 py-1 text-sm font-medium"
              onClick={retryOnClick}
            >
              {retryLabel}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

/* ──────────────────────────────────────────────
   ProgressBar – reusable progress indicator
   ────────────────────────────────────────────── */
export const ProgressBar: FC<{
  value: number; // 0-100
  level?: ProgressLevel;
  height?: number;
  showLabel?: boolean;
  label?: string;
  className?: string;
}> = ({ value, level = "normal", height = 8, showLabel = false, label, className = "" }) => {
  const { resolvedTheme } = useTheme();
  const surfaces = getSurfaceClasses(resolvedTheme);
  const clampedValue = Math.max(0, Math.min(100, value));
  const progressBg = level === "accent" ? "bg-accent" : getProgressClasses(level);

  return (
    <div className={`w-full ${className}`}>
      <div className={`w-full bg-${surfaces.surfaceAlt === "bg-lightSurfaceAlt" ? "lightSurfaceAlt" : "darkSurfaceAlt"} rounded-full overflow-hidden`} style={{ height: `${height}px` }}>
        <div
          className={`h-full ${progressBg} rounded-full transition-all duration-300 ease-in-out`}
          style={{ width: `${clampedValue}%` }}
        />
      </div>
      {showLabel && (
        <div className="mt-1 flex justify-between text-xs">
          <span className={surfaces.textSecondary}>{label || `${clampedValue}%`}</span>
          <span className={surfaces.textSecondary}>{clampedValue}%</span>
        </div>
      )}
    </div>
  );
};

/* ──────────────────────────────────────────────
   DataTable – sortable, filterable table wrapper
   ────────────────────────────────────────────── */
export interface ColumnDef<T> {
  key: string;
  header: string;
  render?: (row: T, index: number) => ReactNode;
  sortable?: boolean;
  width?: string;
}

export const DataTable: FC<{
  columns: ColumnDef<any>[];
  data: any[];
  keyField: string;
  emptyMessage?: string;
  onRowClick?: (row: any) => void;
  striped?: boolean;
  hoverable?: boolean;
}> = ({ columns, data, keyField, emptyMessage = "No data available", onRowClick, striped = true, hoverable = true }) => {
  const { resolvedTheme } = useTheme();
  const surfaces = getSurfaceClasses(resolvedTheme);

  if (data.length === 0) {
    return (
      <div className={`rounded-lg border ${surfaces.border} ${surfaces.surface} p-8 text-center`}>
        <p className={surfaces.textSecondary}>{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" role="grid">
        <thead>
          <tr className={`border-b ${surfaces.border}`}>
            {columns.map((col) => (
              <th
                key={col.key}
                className={`text-left p-3 font-semibold ${surfaces.textPrimary} ${col.sortable ? "cursor-pointer select-none hover:underline" : ""}`}
                style={{ width: col.width }}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, rowIndex) => (
            <tr
              key={row[keyField]}
              className={`border-b ${surfaces.border} ${hoverable ? `hover:${surfaces.surfaceAlt} transition-colors` : ""} ${striped && rowIndex % 2 === 1 ? surfaces.surfaceAlt : ""}`}
              onClick={() => onRowClick && onRowClick(row)}
              style={{ cursor: onRowClick ? "pointer" : "default" }}
            >
              {columns.map((col) => (
                <td key={col.key} className="p-3">
                  {col.render ? col.render(row, rowIndex) : String(row[col.key] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

/* ──────────────────────────────────────────────
   Card – elevated surface with consistent styling
   ────────────────────────────────────────────── */
export const Card: FC<{
  children: ReactNode;
  className?: string;
  elevated?: boolean;
  padding?: number;
}> = ({ children, className = "", elevated = false, padding = 6 }) => {
  const { resolvedTheme } = useTheme();
  const surfaces = getSurfaceClasses(resolvedTheme);
  const elevation = elevated ? "shadow-lg" : "shadow-sm";
  return (
    <div className={`rounded-xl border ${surfaces.border} ${surfaces.surface} ${elevation} p-${padding} ${className}`}>
      {children}
    </div>
  );
};

/* ──────────────────────────────────────────────
   Button – consistent button variants
   ────────────────────────────────────────────── */
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "destructive";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
}

export const Button = ({
  variant = "primary",
  size = "md",
  loading = false,
  disabled,
  children,
  className = "",
  ...props
}: ButtonProps) => {
  const { resolvedTheme } = useTheme();
  const surfaces = getSurfaceClasses(resolvedTheme);

  const baseStyles = "inline-flex items-center justify-center font-medium rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-electricblue focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed";

  const variantStyles = {
    primary: "bg-electricblue text-onAccent hover:bg-electricblueHover active:bg-electricbluePressed",
    secondary: `${surfaces.surfaceAlt} ${surfaces.textPrimary} border ${surfaces.border} hover:${surfaces.surfaceElevated}`,
    ghost: `${surfaces.textPrimary} hover:${surfaces.surfaceAlt}`,
    destructive: "bg-destructive text-white hover:bg-destructiveHover",
  };

  const sizeStyles = {
    sm: "px-3 py-1.5 text-sm",
    md: "px-4 py-2 text-sm",
    lg: "px-6 py-3 text-base",
  };

  return (
    <button
      className={`${baseStyles} ${variantStyles[variant]} ${sizeStyles[size]} ${className}`}
      disabled={disabled || loading}
      {...props}
    >
      {loading && (
        <svg className="animate-spin -ml-1 mr-2 h-4 w-4" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
      )}
      {children}
    </button>
  );
};

/* ──────────────────────────────────────────────
   Input – consistent form input
   ────────────────────────────────────────────── */
export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export const Input = ({ label, error, helperText, className = "", id, ...props }: InputProps) => {
  const { resolvedTheme } = useTheme();
  const surfaces = getSurfaceClasses(resolvedTheme);
  const inputId = id || label?.toLowerCase().replace(/\s+/g, "-");
  const criticalClasses = getSemanticClasses("critical");

  return (
    <div className="w-full">
      {label && (
        <label htmlFor={inputId} className={`block text-sm font-medium ${surfaces.textPrimary} mb-1`}>
          {label}
        </label>
      )}
      <input
        id={inputId}
        className={`
          w-full rounded-lg border px-3 py-2 text-sm transition-colors
          ${surfaces.surface} ${surfaces.border} ${surfaces.textPrimary}
          placeholder:${surfaces.textSecondary}
          focus:outline-none focus:ring-2 focus:ring-electricblue focus:border-transparent
          disabled:bg-${surfaces.surfaceAlt === "bg-lightSurfaceAlt" ? "lightSurfaceAlt" : "darkSurfaceAlt"} disabled:cursor-not-allowed
          ${error ? `border-critical focus:ring-critical ${criticalClasses.border}` : ""}
          ${className}
        `}
        aria-invalid={error ? "true" : "false"}
        aria-describedby={error ? `${inputId}-error` : helperText ? `${inputId}-helper` : undefined}
        {...props}
      />
      {error && (
        <p id={`${inputId}-error`} className="mt-1 text-sm" role="alert">
          <span className={criticalClasses.text}>{error}</span>
        </p>
      )}
      {helperText && !error && (
        <p id={`${inputId}-helper`} className={`mt-1 text-sm ${surfaces.textSecondary}`}>
          {helperText}
        </p>
      )}
    </div>
  );
};

/* ──────────────────────────────────────────────
   Select – consistent select dropdown
   ────────────────────────────────────────────── */
export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
  options: { value: string; label: string }[];
}

export const Select = ({ label, error, options, className = "", id, ...props }: SelectProps) => {
  const { resolvedTheme } = useTheme();
  const surfaces = getSurfaceClasses(resolvedTheme);
  const selectId = id || label?.toLowerCase().replace(/\s+/g, "-");
  const criticalClasses = getSemanticClasses("critical");

  return (
    <div className="w-full">
      {label && (
        <label htmlFor={selectId} className={`block text-sm font-medium ${surfaces.textPrimary} mb-1`}>
          {label}
        </label>
      )}
      <select
        id={selectId}
        className={`
          w-full rounded-lg border px-3 py-2 text-sm transition-colors appearance-none
          ${surfaces.surface} ${surfaces.border} ${surfaces.textPrimary}
          focus:outline-none focus:ring-2 focus:ring-electricblue focus:border-transparent
          disabled:bg-${surfaces.surfaceAlt === "bg-lightSurfaceAlt" ? "lightSurfaceAlt" : "darkSurfaceAlt"} disabled:cursor-not-allowed
          ${error ? `border-critical focus:ring-critical ${criticalClasses.border}` : ""}
          ${className}
        `}
        aria-invalid={error ? "true" : "false"}
        {...props}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      {error && (
        <p className="mt-1 text-sm" role="alert">
          <span className={criticalClasses.text}>{error}</span>
        </p>
      )}
    </div>
  );
};

/* ──────────────────────────────────────────────
   Checkbox – consistent checkbox
   ────────────────────────────────────────────── */
export interface CheckboxProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "type"> {
  label: string;
}

export const Checkbox = ({ label, className = "", id, ...props }: CheckboxProps) => {
  const { resolvedTheme } = useTheme();
  const surfaces = getSurfaceClasses(resolvedTheme);
  const checkboxId = id || label.toLowerCase().replace(/\s+/g, "-");

  return (
    <label className="flex items-center gap-2 cursor-pointer" htmlFor={checkboxId}>
      <input
        type="checkbox"
        id={checkboxId}
        className={`
          h-4 w-4 rounded border-2 transition-colors cursor-pointer
          ${surfaces.border} ${surfaces.surface}
          focus:outline-none focus:ring-2 focus:ring-electricblue focus:ring-offset-2
          checked:bg-electricblue checked:border-electricblue checked:text-onAccent
          disabled:opacity-50 disabled:cursor-not-allowed
          ${className}
        `}
        {...props}
      />
      <span className={`text-sm ${surfaces.textPrimary}`}>{label}</span>
    </label>
  );
};

/* ──────────────────────────────────────────────
   Toggle – on/off switch
   ────────────────────────────────────────────── */
export interface ToggleProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "type"> {
  label?: string;
}

export const Toggle = ({ label, className = "", id, ...props }: ToggleProps) => {
  const { resolvedTheme } = useTheme();
  const surfaces = getSurfaceClasses(resolvedTheme);
  const toggleId = id || label?.toLowerCase().replace(/\s+/g, "-");

  return (
    <label className="flex items-center gap-3 cursor-pointer" htmlFor={toggleId}>
      <input
        type="checkbox"
        id={toggleId}
        className={`
          h-5 w-9 appearance-none rounded-full relative cursor-pointer transition-colors
          bg-${surfaces.surfaceAlt === "bg-lightSurfaceAlt" ? "lightSurfaceAlt" : "darkSurfaceAlt"} border ${surfaces.border}
          focus:outline-none focus:ring-2 focus:ring-electricblue focus:ring-offset-2
          checked:bg-electricblue checked:border-electricblue
          disabled:opacity-50 disabled:cursor-not-allowed
          after:content-[''] after:absolute after:top-0.5 after:left-0.5 after:h-4 after:w-4 after:rounded-full after:bg-white after:shadow-md after:transition-transform
          checked:after:translate-x-4
          ${className}
        `}
        {...props}
      />
      {label && <span className={`text-sm ${surfaces.textPrimary}`}>{label}</span>}
    </label>
  );
};

/* ──────────────────────────────────────────────
   ErrorBoundary – catches render errors in children
   ────────────────────────────────────────────── */
interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("ErrorBoundary caught an error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }
      return (
        <div className="rounded-lg border border-red-500/30 bg-red-50 dark:bg-red-900/20 p-6">
          <div className="flex">
            <div className="flex-shrink-0">
              <svg className="w-5 h-5 text-red-500" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <div className="ml-3">
              <h4 className="text-sm font-medium text-red-500">Something went wrong</h4>
              <p className="text-sm mt-1 text-slate-500 dark:text-slate-400">
                {this.state.error?.message || "An unexpected error occurred"}
              </p>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}