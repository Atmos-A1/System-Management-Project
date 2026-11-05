import { useEffect, useState, useCallback } from "react";
import { MetricCard } from "./MetricCard";
import { invokeMetric } from "../lib/invoke";
import { useTheme } from "../context/ThemeContext";

interface MetricData {
  cpu?: number;
  ram?: { total: number; available: number; used: number; percent: number };
  disk?: { total: number; used: number; free: number; percent: number };
  battery?: { percent: number; secsleft: number; power_plugged: boolean } | {};
}

export function Dashboard() {
  const [data, setData] = useState<MetricData>({});
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const { resolvedTheme } = useTheme();

  const fetchMetrics = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Fetch all four metrics in parallel, correlating by request ID.
      const [cpu, ram, disk, battery] = await Promise.all([
        invokeMetric({ method: "system_monitor.get_cpu_percent", params: {} }),
        invokeMetric({ method: "system_monitor.get_ram_usage", params: {} }),
        invokeMetric({ method: "system_monitor.get_disk_usage", params: { path: "/" } }),
        invokeMetric({ method: "system_monitor.get_battery_info", params: {} }),
      ]);

      setData({
        cpu: cpu as number,
        ram: ram as MetricData["ram"],
        disk: disk as MetricData["disk"],
        battery: battery as MetricData["battery"],
      });
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to fetch metrics from sidecar",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMetrics();
    // Poll every 5 seconds to match the existing PySide6 refresh interval.
    const timer = setInterval(fetchMetrics, 5000);
    return () => clearInterval(timer);
  }, [fetchMetrics]);

  const isDark = resolvedTheme === "dark";

  return (
    <div className="min-h-screen transition-colors duration-300">
      {/* Header */}
      <header className="border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50">
        <div className="flex items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <div
              className="w-8 h-8 rounded-lg bg-blue-600 dark:bg-blue-500 flex items-center justify-center text-white shadow-lg shadow-blue-500/30"
            >
              <svg
                className="w-5 h-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M13 10V3L4 14h7v7l9-11h-7z"
                />
              </svg>
            </div>
            <div>
              <h1 className="text-xl font-semibold tracking-tight">Panther System Intelligence</h1>
              <p className="text-sm text-slate-500 dark:text-slate-400">
                System dashboard • {isDark ? "Dark" : "Light"} mode
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                // Theme switching is handled by the ThemeProvider in App
              }}
              className="p-2 rounded-md hover:bg-slate-200 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-400"
              title="Toggle theme"
            >
              <svg
                className="w-5 h-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"
                />
              </svg>
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8">
        {/* Error banner */}
        {error && (
          <div className="rounded-md border border-red-200 bg-red-50 p-4 mb-6">
            <div className="flex">
              <div className="flex-shrink-0">
                <svg className="w-5 h-5 text-red-500" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 2v2m0 18v-2M4.93 4.93l√2 1.41m14.142 14.141-√2 1.41M12 12v2m0-12v2m-6.343 4.343l√2 1.41m14.142-14.141l√2 -1.41M12 16h.01M12 8h.01" />
                </svg>
              </div>
              <div className="ml-3">
                <h4 className="text-sm font-medium text-red-800">Sidecar error</h4>
                <p className="text-sm text-red-600">{error}</p>
              </div>
            </div>
          </div>
        )}

        {/* Loading state */}
        {loading && !error && (
          <div className="flex flex-col items-center justify-center py-20">
            <div className="flex h-8 w-8 rounded-full ring-4 ring-blue-200 dark:ring-slate-800">
              <div className="h-8 w-8 rounded-full ring-4 ring-blue-600 dark:ring-blue-500 ring-opacity-75 animate-[spin_1.2s_linear_infinite]"></div>
            </div>
            <p className="mt-4 text-slate-500 dark:text-slate-400">
              Connecting to sidecar…
            </p>
          </div>
        )}

        {/* Metrics grid */}
        {!loading && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <MetricCard
              title="CPU"
              subtitle="Processor usage"
              value={data.cpu !== undefined ? `${data.cpu.toFixed(1)}%` : "—"}
              detail="Current CPU utilisation"

            />
            <MetricCard
              title="Memory"
              subtitle="RAM usage"
              value={data.ram ? `${data.ram.percent.toFixed(1)}%` : "—"}
              detail={
                data.ram
                  ? `${(data.ram.used / 1024 / 1024 / 1024).toFixed(1)} GB / ${(data.ram.total / 1024 / 1024 / 1024).toFixed(1)} GB`
                  : "—"
              }

            />
            <MetricCard
              title="Storage"
              subtitle="Disk usage"
              value={data.disk ? `${data.disk.percent.toFixed(1)}%` : "—"}
              detail={
                data.disk
                  ? `${(data.disk.used / 1024 / 1024 / 1024).toFixed(1)} GB / ${(data.disk.total / 1024 / 1024 / 1024).toFixed(1)} GB`
                  : "—"
              }

            />
            <MetricCard
              title="Battery"
              subtitle="Battery status"
              value={
                data.battery && "percent" in data.battery
                  ? `${data.battery.percent.toFixed(0)}%`
                  : "N/A"
              }
              detail={
                data.battery && "power_plugged" in data.battery
                  ? data.battery.power_plugged
                    ? "Charging (AC power)"
                    : "Discharging (on battery)"
                  : "No battery detected"
              }

            />
          </div>
        )}
      </main>
    </div>
  );
}
