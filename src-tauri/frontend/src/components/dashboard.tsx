import { useEffect, useState, useCallback } from "react";
import { invokeMetric } from "../lib/invoke";
import { useTheme } from "../context/ThemeContext";
import { useNav } from "../App";
import {
  PageScaffold,
  Toolbar,
  Badge,
  MetricCard,
  SectionCard,
  EmptyState,
  LoadingState,
  ErrorState,
  ProgressBar,
  Button,
  ErrorBoundary,
} from "../components/shared";

interface MetricData {
  cpu?: number | null;
  ram?: { total: number; available: number; used: number; percent: number } | null;
  disk?: { total: number; used: number; free: number; percent: number } | null;
  battery?: { percent: number; secsleft: number; power_plugged: boolean; status?: string } | {} | null;
  uptime?: string | null;
  os?: string | null;
  hostname?: string | null;
  lastUpdated?: string;
}

interface Recommendation {
  id: string;
  title: string;
  description: string;
  action?: string;
  actionTarget?: string;
  level: "normal" | "warning" | "critical";
  category: "performance" | "storage" | "battery" | "startup" | "security";
}

interface ActivityLog {
  id: number;
  timestamp: string;
  level: "info" | "warning" | "critical";
  message: string;
  component: string;
}

/** Dashboard – balanced system intelligence screen. */
export function Dashboard() {
  const [data, setData] = useState<MetricData>({
    lastUpdated: "—",
  });
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [recommendationsError, setRecommendationsError] = useState<string | null>(null);
  const [activityHistory, setActivityHistory] = useState<ActivityLog[]>([]);
  const [activityError, setActivityError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const { resolvedTheme } = useTheme();
  const { setCurrentScreen } = useNav();

  const fetchMetrics = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const results = await Promise.allSettled([
        invokeMetric({ method: "system_monitor.get_cpu_percent", params: {} }),
        invokeMetric({ method: "system_monitor.get_ram_usage", params: {} }),
        invokeMetric({ method: "system_monitor.get_disk_usage", params: {} }),
        invokeMetric({ method: "system_monitor.get_battery_info", params: {} }),
        invokeMetric({ method: "system_monitor.uptime", params: {} }),
        invokeMetric({ method: "system_monitor.operating_system", params: {} }),
        invokeMetric({ method: "system_monitor.hostname", params: {} }),
      ]);

      const [cpu, ram, disk, battery, uptime, os, hostname] = results.map((r) =>
        r.status === "fulfilled" ? r.value : null
      );

      setData({
        cpu: cpu as number | null,
        ram: ram as MetricData["ram"],
        disk: disk as MetricData["disk"],
        battery: (battery as MetricData["battery"]) || {},
        uptime: uptime as string | null,
        os: os as string | null,
        hostname: hostname as string | null,
        lastUpdated: new Date().toLocaleTimeString(),
      });

      // Check if any critical metrics failed
      const failed = results.filter((r) => r.status === "rejected").length;
      if (failed > 0) {
        const messages = results
          .filter((r) => r.status === "rejected")
          .map((r) => (r as PromiseRejectedResult).reason?.message || "Unknown error")
          .join("; ");
        setError(`Some metrics unavailable: ${messages}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch metrics from sidecar");
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchRecommendations = useCallback(async () => {
    try {
      const recs = await invokeMetric({
        method: "system_monitor.get_recommendations",
        params: {},
      });
      setRecommendations(recs as Recommendation[]);
      setRecommendationsError(null);
    } catch (err) {
      setRecommendationsError(err instanceof Error ? err.message : "Failed to fetch recommendations");
    }
  }, []);

  const fetchActivityHistory = useCallback(async () => {
    try {
      const logs = await invokeMetric({
        method: "system_monitor.get_activity_history",
        params: { limit: 10 },
      });
      setActivityHistory(logs as ActivityLog[]);
      setActivityError(null);
    } catch (err) {
      setActivityError(err instanceof Error ? err.message : "Failed to fetch activity history");
    }
  }, []);

  useEffect(() => {
    fetchMetrics();
    fetchRecommendations();
    fetchActivityHistory();
    const timer = setInterval(() => {
      fetchMetrics();
      fetchRecommendations();
      fetchActivityHistory();
    }, 5000);
    return () => clearInterval(timer);
  }, [fetchMetrics, fetchRecommendations, fetchActivityHistory]);

  const isDark = resolvedTheme === "dark";

  /* State colour mapping - null-safe guards */
  const hasCritical =
    (data.cpu != null && data.cpu >= 85) ||
    (data.ram?.percent != null && data.ram.percent >= 90) ||
    (data.disk?.percent != null && data.disk.percent >= 85);
  const hasWarning =
    (data.cpu != null && data.cpu >= 65) ||
    (data.ram?.percent != null && data.ram.percent >= 80) ||
    (data.disk?.percent != null && data.disk.percent >= 65);

  const healthStatus = hasCritical ? "critical" : hasWarning ? "warning" : "success";
  const healthLabel = hasCritical ? "Critical" : hasWarning ? "Warning" : "Healthy";

  return (
    <ErrorBoundary>
      <div className="min-h-screen">
        {/* ----- System Identity & Overall Status (top region) ----- */}
        <section className="mb-8">
          <PageScaffold title="System Dashboard" subtitle="Real-time monitoring of your system resources">
            <Toolbar>
              <Badge text={healthLabel} status={healthStatus as "critical" | "warning" | "success"} variant="flat" />
              <span className="ml-4 text-sm text-slate-500 dark:text-slate-400">
                Last updated {data.lastUpdated}
              </span>
            </Toolbar>

            <SectionCard title="System Identity" subtitle="Device and operating system information">
              <div className="grid grid-cols-2 gap-4 md:grid-cols-4 text-sm">
                <div>
                  <div className="text-slate-500 dark:text-slate-400">Hostname</div>
                  <div className="font-medium text-slate-900 dark:text-white">
                    {data.hostname || "—"}
                  </div>
                </div>
                <div>
                  <div className="text-slate-500 dark:text-slate-400">OS</div>
                  <div className="font-medium text-slate-900 dark:text-white">
                    {data.os || "—"}
                  </div>
                </div>
                <div>
                  <div className="text-slate-500 dark:text-slate-400">Uptime</div>
                  <div className="font-medium text-slate-900 dark:text-white">
                    {data.uptime || "—"}
                  </div>
                </div>
                <div>
                  <div className="text-slate-500 dark:text-slate-400">Arch</div>
                  <div className="font-medium text-slate-900 dark:text-white">
                    {typeof navigator !== "undefined" ? navigator.platform || "—" : "—"}
                  </div>
                </div>
              </div>
            </SectionCard>

            <SectionCard title="System Health" subtitle="Important warnings and operational information">
              <div className="grid grid-cols-3 gap-4">
                <Badge text={healthLabel} status={healthStatus as "critical" | "warning" | "success"} variant="pill" className="w-full py-3 text-base" />
                <div className="col-span-2">
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <div className={`p-2 rounded ${hasCritical ? "bg-critical/10 border border-critical" : hasWarning ? "bg-warning/10 border border-warning" : "bg-healthy/10 border border-healthy"}`}>
                      <div className="font-medium">CPU</div>
                      <div className="text-xs text-slate-500 dark:text-slate-400">
                        {data.cpu != null ? `${data.cpu.toFixed(1)}%` : "—"}
                      </div>
                    </div>
                    <div className={`p-2 rounded ${hasCritical ? "bg-critical/10 border border-critical" : hasWarning ? "bg-warning/10 border border-warning" : "bg-healthy/10 border border-healthy"}`}>
                      <div className="font-medium">Memory</div>
                      <div className="text-xs text-slate-500 dark:text-slate-400">
                        {data.ram?.percent != null ? `${data.ram.percent.toFixed(1)}%` : "—"}
                      </div>
                    </div>
                    <div className={`p-2 rounded ${hasCritical ? "bg-critical/10 border border-critical" : hasWarning ? "bg-warning/10 border border-warning" : "bg-healthy/10 border border-healthy"}`}>
                      <div className="font-medium">Storage</div>
                      <div className="text-xs text-slate-500 dark:text-slate-400">
                        {data.disk?.percent != null ? `${data.disk.percent.toFixed(1)}%` : "—"}
                      </div>
                    </div>
                    <div className={`p-2 rounded ${data.battery && "percent" in data.battery && data.battery.percent <= 10 ? "bg-critical/10 border border-critical" : data.battery && "percent" in data.battery && data.battery.percent <= 20 ? "bg-warning/10 border border-warning" : "bg-healthy/10 border border-healthy"}`}>
                      <div className="font-medium">Battery</div>
                      <div className="text-xs text-slate-500 dark:text-slate-400">
                        {data.battery && "percent" in data.battery ? `${data.battery.percent.toFixed(0)}%` : "N/A"}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </SectionCard>
          </PageScaffold>
        </section>

        {/* ----- Prominent System Overview (resource intelligence) ----- */}
        <section className="mb-8">
          <PageScaffold title="Resource Intelligence" subtitle="CPU, memory, storage and network utilisation">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
              <MetricCard
                title="CPU"
                subtitle="Processor usage"
                value={data.cpu != null ? `${data.cpu.toFixed(1)}%` : "—"}
                detail="Current CPU utilisation"
                showProgress
                progressLevel={
                  data.cpu != null
                    ? data.cpu >= 85
                      ? "critical"
                      : data.cpu >= 65
                      ? "warning"
                      : "normal"
                    : undefined
                }
              />
              <MetricCard
                title="Memory (RAM)"
                subtitle="Memory usage"
                value={data.ram?.percent != null ? `${data.ram.percent.toFixed(1)}%` : "—"}
                detail={
                  data.ram
                    ? `${(data.ram.used / 1024 / 1024 / 1024).toFixed(1)} GB / ${(data.ram.total / 1024 / 1024 / 1024).toFixed(1)} GB`
                    : "—"
                }
                showProgress
                progressLevel={
                  data.ram?.percent != null
                    ? data.ram.percent >= 90
                      ? "critical"
                      : data.ram.percent >= 80
                      ? "warning"
                      : "normal"
                    : undefined
                }
              />
              <MetricCard
                title="Storage"
                subtitle="Disk usage"
                value={data.disk?.percent != null ? `${data.disk.percent.toFixed(1)}%` : "—"}
                detail={
                  data.disk
                    ? `${(data.disk.used / 1024 / 1024 / 1024).toFixed(1)} GB / ${(data.disk.total / 1024 / 1024 / 1024).toFixed(1)} GB`
                    : "—"
                }
                showProgress
                progressLevel={
                  data.disk?.percent != null
                    ? data.disk.percent >= 85
                      ? "critical"
                      : data.disk.percent >= 65
                      ? "warning"
                      : "normal"
                    : undefined
                }
              />
              {data.battery && "percent" in data.battery && (
                <MetricCard
                  title="Battery"
                  subtitle={data.battery.status || (data.battery.power_plugged ? "Charging (AC power)" : "Discharging (on battery)")}
                  value={data.battery.percent.toFixed(0) + "%"}
                  detail={
                    data.battery.power_plugged ? "Charging (AC power)" : "Discharging (on battery)"
                  }
                  showProgress
                  progressLevel={
                    data.battery.percent <= 10
                      ? "critical"
                      : data.battery.percent <= 20
                      ? "warning"
                      : "normal"
                  }
                />
              )}
            </div>
          </PageScaffold>
        </section>

        {/* ----- Storage & Recommendations (supporting regions) ----- */}
        <section className="grid grid-cols-1 gap-6 md:grid-cols-2">
          <SectionCard title="Storage Intelligence" subtitle="Capacity and available space">
            <div className="grid grid-cols-2 gap-4">
              <div className="p-4 rounded-lg border bg-slate-950 dark:bg-slate-900 text-white">
                <div className="text-3xl font-bold">
                  {data.disk ? `${(data.disk.free / 1024 / 1024 / 1024).toFixed(1)} GB` : "— GB"}
                </div>
                <div className="text-slate-400">Available</div>
              </div>
              <div className="p-4 rounded-lg border bg-slate-950 dark:bg-slate-900 text-white">
                <div className="text-3xl font-bold">
                  {data.disk ? `${(data.disk.used / 1024 / 1024 / 1024).toFixed(1)} GB` : "— GB"}
                </div>
                <div className="text-slate-400">Used</div>
              </div>
            </div>
            <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
              Click below to explore storage in detail.
            </p>
            <Button
              variant="primary"
              className="mt-3 w-full"
              onClick={() => setCurrentScreen && setCurrentScreen("Storage")}
            >
              Explore Storage
            </Button>
          </SectionCard>

          <SectionCard title="Recommendations and Attention" subtitle="Actionable, explainable recommendations">
            {recommendationsError ? (
              <div className="p-3 rounded-lg bg-critical/10 border border-critical/20">
                <div className="flex items-center gap-2 text-critical">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
                  <span className="text-sm font-medium">Recommendations unavailable:</span>
                  <span className="text-sm">{recommendationsError}</span>
                </div>
              </div>
            ) : recommendations.length === 0 ? (
              <p className="text-sm text-slate-500 dark:text-slate-400">
                No recommendations at this time. All system metrics are within normal operating parameters.
              </p>
            ) : (
              <div className="space-y-3">
                {recommendations.slice(0, 3).map((rec) => (
                  <div
                    key={rec.id}
                    className={`p-3 rounded-lg border-l-4 ${
                      rec.level === "critical"
                        ? "bg-critical/10 border-critical"
                        : rec.level === "warning"
                        ? "bg-warning/10 border-warning"
                        : "bg-healthy/10 border-healthy"
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      <Badge
                        text={rec.level.charAt(0).toUpperCase() + rec.level.slice(1)}
                        status={rec.level === "critical" ? "critical" : rec.level === "warning" ? "warning" : "success"}
                        variant="flat"
                      />
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-sm text-slate-900 dark:text-white">{rec.title}</p>
                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{rec.description}</p>
                      </div>
                    </div>
                  </div>
                ))}
                {recommendations.length > 3 && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="w-full mt-2"
                    onClick={() => setCurrentScreen && setCurrentScreen("Recommendations")}
                  >
                    View all {recommendations.length} recommendations →
                  </Button>
                )}
              </div>
            )}
          </SectionCard>
        </section>

        {/* ----- Recent Activity (lower section) ----- */}
        {error ? (
          <ErrorState
            title="Error loading dashboard"
            description={error}
            retryLabel="Retry"
            retryOnClick={fetchMetrics}
          />
        ) : loading ? (
          <LoadingState size="sm" />
        ) : (
          <SectionCard title="Recent Activity" subtitle="Relevant system events and application activity">
            {activityError ? (
              <div className="p-3 rounded-lg bg-critical/10 border border-critical/20">
                <div className="flex items-center gap-2 text-critical">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
                  <span className="text-sm font-medium">Recent activity unavailable:</span>
                  <span className="text-sm">{activityError}</span>
                </div>
              </div>
            ) : activityHistory.length === 0 ? (
              <p className="text-sm text-slate-500 dark:text-slate-400">
                No recent activity recorded. Check the Activity History screen for historical data.
              </p>
            ) : (
              <div className="space-y-2">
                {activityHistory.map((log) => (
                  <div
                    key={log.id}
                    className={`p-3 rounded-lg border ${
                      log.level === "critical"
                        ? "bg-critical/5 border-critical/20"
                        : log.level === "warning"
                        ? "bg-warning/5 border-warning/20"
                        : "bg-slate-50 dark:bg-slate-900/50 border-slate-200 dark:border-slate-800"
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      <span
                        className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${
                          log.level === "critical"
                            ? "bg-critical"
                            : log.level === "warning"
                            ? "bg-warning"
                            : "bg-slate-400"
                        }`}
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs text-slate-500 dark:text-slate-400">
                            {new Date(log.timestamp).toLocaleTimeString()}
                          </span>
                          <Badge
                            text={log.level.charAt(0).toUpperCase() + log.level.slice(1)}
                            status={log.level === "critical" ? "critical" : log.level === "warning" ? "warning" : "info"}
                            variant="flat"
                          />
                        </div>
                        <p className="mt-1 text-sm text-slate-900 dark:text-white">{log.message}</p>
                        <div className="mt-1 text-xs text-slate-500 dark:text-slate-400 font-mono">{log.component}</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </SectionCard>
        )}
      </div>
    </ErrorBoundary>
  );
}