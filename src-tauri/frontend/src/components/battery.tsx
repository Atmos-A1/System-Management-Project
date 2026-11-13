import { useEffect, useState, useCallback } from "react";
import { invokeMetric } from "../lib/invoke";
import { useTheme } from "../context/ThemeContext";
import {
  PageScaffold,
  Toolbar,
  Badge,
  SectionCard,
  EmptyState,
  LoadingState,
  ErrorState,
  ProgressBar,
  Button,
  Card,
} from "../components/shared";

interface BatteryInfo {
  percent: number;
  secsleft: number;
  power_plugged: boolean;
  status: "charging" | "discharging" | "full" | "unknown";
}

export function Battery() {
  const [data, setData] = useState<BatteryInfo | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const { resolvedTheme } = useTheme();

  const fetchBattery = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const battery = await invokeMetric({
        method: "system_monitor.get_battery_info",
        params: {},
      });
      setData(battery as BatteryInfo);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch battery info");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchBattery();
    const timer = setInterval(fetchBattery, 30000);
    return () => clearInterval(timer);
  }, [fetchBattery]);

  if (loading) {
    return (
      <PageScaffold title="Battery" subtitle="Battery status and power management">
        <LoadingState size="md" />
      </PageScaffold>
    );
  }

  if (error) {
    return (
      <PageScaffold title="Battery" subtitle="Battery status and power management">
        <ErrorState
          title="Error loading battery"
          description={error}
          retryLabel="Retry"
          retryOnClick={fetchBattery}
        />
      </PageScaffold>
    );
  }

  // No battery detected - honest empty state
  if (!data || Object.keys(data).length === 0) {
    return (
      <PageScaffold title="Battery" subtitle="Battery status and power management">
        <EmptyState
          icon={<svg className="w-12 h-12 mx-auto text-slate-400 dark:text-slate-500" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>}
          title="No battery found"
          description="No battery detected. The system may be running without a battery (e.g., desktop PC)."
        />
      </PageScaffold>
    );
  }

  const { percent, secsleft, power_plugged, status } = data;
  const isCharging = power_plugged;
  const minutesLeft = secsleft >= 0 ? Math.floor(secsleft / 60) : -1;

  const getBatteryLevel = (p: number): "normal" | "warning" | "critical" => {
    if (p <= 10) return "critical";
    if (p <= 20) return "warning";
    return "normal";
  };

  const batteryLevel = getBatteryLevel(percent);
  const statusLabel = {
    charging: "Charging",
    discharging: "Discharging",
    full: "Full",
    unknown: "Unknown",
  }[status] || status;

  return (
    <PageScaffold title="Battery" subtitle="Battery status and power management">
      <Toolbar>
        <Badge
          text={`${percent.toFixed(0)}% ${isCharging ? "⚡" : ""}`}
          status={batteryLevel === "critical" ? "critical" : batteryLevel === "warning" ? "warning" : "success"}
          variant="flat"
        />
        <span className="ml-4 text-sm text-slate-500 dark:text-slate-400">
          {statusLabel} • {isCharging ? "AC Power" : "On Battery"}
        </span>
      </Toolbar>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main battery display */}
        <SectionCard title="Battery Level" subtitle={isCharging ? "Charging" : "On battery power"}>
          <div className="text-center py-8">
            <div className="relative inline-block">
              <svg width="160" height="160" viewBox="0 0 160 160">
                <circle
                  cx="80"
                  cy="80"
                  r="70"
                  fill="none"
                  stroke="#E2E8F0"
                  strokeWidth="12"
                  className="dark:stroke-slate-800"
                />
                <circle
                  cx="80"
                  cy="80"
                  r="70"
                  fill="none"
                  strokeWidth="12"
                  strokeLinecap="round"
                  strokeDasharray={439.8}
                  strokeDashoffset={439.8 * (1 - percent / 100)}
                  className={`transition-all duration-500 ${
                    batteryLevel === "critical"
                      ? "stroke-critical"
                      : batteryLevel === "warning"
                      ? "stroke-warning"
                      : "stroke-healthy"
                  }`}
                  style={{ transform: "rotate(-90deg)", transformOrigin: "center" }}
                />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-5xl font-bold text-slate-900 dark:text-white">{percent.toFixed(0)}%</span>
                <span className="text-sm text-slate-500 dark:text-slate-400">{isCharging ? "Charging" : "Discharging"}</span>
              </div>
            </div>
            <ProgressBar value={percent} level={batteryLevel} height={12} className="mt-6 max-w-xs mx-auto" />
          </div>

          <div className="grid grid-cols-3 gap-4 mt-6 text-center">
            <div className="p-3 rounded-lg bg-slate-950 dark:bg-slate-900">
              <div className="font-mono text-lg text-slate-900 dark:text-white">{statusLabel}</div>
              <div className="text-xs text-slate-500 dark:text-slate-400">Status</div>
            </div>
            <div className="p-3 rounded-lg bg-slate-950 dark:bg-slate-900">
              <div className="font-mono text-lg text-slate-900 dark:text-white">{isCharging ? "AC Power" : "Battery"}</div>
              <div className="text-xs text-slate-500 dark:text-slate-400">Power Source</div>
            </div>
            {secsleft >= 0 && (
              <div className="p-3 rounded-lg bg-slate-950 dark:bg-slate-900">
                <div className="font-mono text-lg text-slate-900 dark:text-white">{minutesLeft > 0 ? `${minutesLeft} min` : "Calculating…"}</div>
                <div className="text-xs text-slate-500 dark:text-slate-400">Time Left</div>
              </div>
            )}
          </div>
        </SectionCard>

        {/* Power Management Options - Not available via backend */}
        <SectionCard title="Power Management" subtitle="System power settings (not controllable via Panther)">
          <div className="space-y-4">
            <Card>
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium">Power Saver Mode</div>
                  <div className="text-sm text-slate-500 dark:text-slate-400">Reduce background activity to extend battery life</div>
                </div>
                <input
                  type="checkbox"
                  disabled
                  className="h-5 w-9 appearance-none rounded-full relative cursor-not-allowed opacity-50 transition-colors bg-slate-300 dark:bg-slate-600"
                />
              </div>
            </Card>
            <Card>
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium">Adaptive Brightness</div>
                  <div className="text-sm text-slate-500 dark:text-slate-400">Automatically adjust screen brightness based on ambient light</div>
                </div>
                <input
                  type="checkbox"
                  disabled
                  className="h-5 w-9 appearance-none rounded-full relative cursor-not-allowed opacity-50 transition-colors bg-slate-300 dark:bg-slate-600"
                />
              </div>
            </Card>
            <Card>
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium">Sleep on Lid Close</div>
                  <div className="text-sm text-slate-500 dark:text-slate-400">Put system to sleep when laptop lid is closed</div>
                </div>
                <input
                  type="checkbox"
                  disabled
                  className="h-5 w-9 appearance-none rounded-full relative cursor-not-allowed opacity-50 transition-colors bg-slate-300 dark:bg-slate-600"
                />
              </div>
            </Card>
            <Card>
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium">USB Selective Suspend</div>
                  <div className="text-sm text-slate-500 dark:text-slate-400">Allow USB ports to enter low-power state when idle</div>
                </div>
                <input
                  type="checkbox"
                  disabled
                  className="h-5 w-9 appearance-none rounded-full relative cursor-not-allowed opacity-50 transition-colors bg-slate-300 dark:bg-slate-600"
                />
              </div>
            </Card>
            <p className="text-xs text-slate-500 dark:text-slate-400 text-center">
              These settings are managed by the OS and cannot be controlled by Panther.
            </p>
          </div>
        </SectionCard>

        {/* Battery Health & Details */}
        <SectionCard title="Battery Health" subtitle="Capacity and cycle information">
          <div className="space-y-4">
            <Card>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-sm text-slate-500 dark:text-slate-400">Design Capacity</div>
                  <div className="font-mono text-lg text-slate-900 dark:text-white">— mWh</div>
                </div>
                <div>
                  <div className="text-sm text-slate-500 dark:text-slate-400">Full Charge Capacity</div>
                  <div className="font-mono text-lg text-slate-900 dark:text-white">— mWh</div>
                </div>
                <div>
                  <div className="text-sm text-slate-500 dark:text-slate-400">Cycle Count</div>
                  <div className="font-mono text-lg text-slate-900 dark:text-white">—</div>
                </div>
                <div>
                  <div className="text-sm text-slate-500 dark:text-slate-400">Health</div>
                  <div className="font-mono text-lg text-slate-900 dark:text-white">—%</div>
                </div>
              </div>
            </Card>

            <Card>
              <div className="text-sm text-slate-500 dark:text-slate-400 mb-2">Charging History (last 7 days)</div>
              <div className="h-32 flex items-end justify-between gap-1">
                {/* Honest empty state - no fabricated data */}
                <div className="flex-1 rounded-t bg-slate-200 dark:bg-slate-700" title="No data available" />
                <div className="flex-1 rounded-t bg-slate-200 dark:bg-slate-700" title="No data available" />
                <div className="flex-1 rounded-t bg-slate-200 dark:bg-slate-700" title="No data available" />
                <div className="flex-1 rounded-t bg-slate-200 dark:bg-slate-700" title="No data available" />
                <div className="flex-1 rounded-t bg-slate-200 dark:bg-slate-700" title="No data available" />
                <div className="flex-1 rounded-t bg-slate-200 dark:bg-slate-700" title="No data available" />
                <div className="flex-1 rounded-t bg-slate-200 dark:bg-slate-700" title="No data available" />
              </div>
              <p className="mt-2 text-xs text-slate-500 dark:text-slate-400 text-center">
                Charging history not available from system APIs
              </p>
            </Card>

            <Button variant="secondary" className="w-full" disabled>
              Run Battery Calibration
            </Button>
            <Button variant="ghost" className="w-full" disabled>
              View Detailed Report
            </Button>
          </div>
        </SectionCard>
      </div>
    </PageScaffold>
  );
}