import { useEffect, useState, useCallback } from "react";
import { invokeMetric } from "../lib/invoke";
import { useTheme } from "../context/ThemeContext";
import {
  PageScaffold,
  Toolbar,
  Badge,
  SectionCard,
  LoadingState,
  ErrorState,
  ProgressBar,
  Button,
  Toggle,
  Card,
} from "../components/shared";

interface AdaptiveConfig {
  cpuThreshold: number;
  memoryThreshold: number;
  autoShutdown: boolean;
  enabled: boolean;
  aggressiveMode: boolean;
  notifyOnAction: boolean;
}

export function AdaptiveControl() {
  const [data, setData] = useState<AdaptiveConfig>({
    cpuThreshold: 85,
    memoryThreshold: 90,
    autoShutdown: false,
    enabled: true,
    aggressiveMode: false,
    notifyOnAction: true,
  });
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const { resolvedTheme } = useTheme();

  const fetchAdaptiveControl = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const config = await invokeMetric({
        method: "system_monitor.get_adaptive_control",
        params: {},
      });
      setData(config as AdaptiveConfig);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch adaptive control settings");
      // Use defaults on error
      setData({
        cpuThreshold: 85,
        memoryThreshold: 90,
        autoShutdown: false,
        enabled: true,
        aggressiveMode: false,
        notifyOnAction: true,
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAdaptiveControl();
  }, [fetchAdaptiveControl]);

  const handleSave = async () => {
    setSaving(true);
    setSaved(false);
    try {
      await invokeMetric({
        method: "system_monitor.set_adaptive_control",
        params: {
          cpuThreshold: data.cpuThreshold,
          memoryThreshold: data.memoryThreshold,
          autoShutdown: data.autoShutdown,
          enabled: data.enabled,
          aggressiveMode: data.aggressiveMode,
          notifyOnAction: data.notifyOnAction,
        },
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    setData({
      cpuThreshold: 85,
      memoryThreshold: 90,
      autoShutdown: false,
      enabled: true,
      aggressiveMode: false,
      notifyOnAction: true,
    });
  };

  if (loading) {
    return (
      <PageScaffold title="Adaptive Control" subtitle="Automated system response settings">
        <LoadingState size="md" />
      </PageScaffold>
    );
  }

  if (error) {
    return (
      <PageScaffold title="Adaptive Control" subtitle="Automated system response settings">
        <ErrorState
          title="Error loading adaptive control"
          description={error}
          retryLabel="Retry"
          retryOnClick={fetchAdaptiveControl}
        />
      </PageScaffold>
    );
  }

  const statusColor = data.enabled ? "success" : "warning";
  const statusLabel = data.enabled ? "Active" : "Disabled";
  const statusDescription = data.enabled
    ? "Automated responses are enabled (Panther app preferences only — no system enforcement)"
    : "Automated responses are disabled. No automatic action will be taken.";

  return (
    <PageScaffold title="Adaptive Control" subtitle="Automated system response settings (Panther app preferences only)">
      <Toolbar>
        <Badge text={statusLabel} status={statusColor as "success" | "warning"} variant="flat" />
        <span className="ml-4 text-sm text-slate-500 dark:text-slate-400">
          {statusDescription}
        </span>
      </Toolbar>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main configuration */}
        <SectionCard title="Threshold Configuration" subtitle="Set resource limits for automated responses (app-level only)" className="lg:col-span-2">
          <Card>
            <div className="mb-6">
              <div className="flex items-center justify-between mb-2">
                <label className="block text-sm font-medium">CPU Threshold</label>
                <span className="font-mono text-lg">{data.cpuThreshold}%</span>
              </div>
              <ProgressBar
                value={data.cpuThreshold}
                level={data.cpuThreshold >= 85 ? "critical" : data.cpuThreshold >= 65 ? "warning" : "normal"}
                height={8}
              />
              <input
                type="range"
                min="0"
                max="100"
                value={data.cpuThreshold}
                onChange={(e) => setData({ ...data, cpuThreshold: Number(e.target.value) })}
                className="w-full mt-2 h-2 bg-slate-200 dark:bg-slate-700 rounded-lg appearance-none cursor-pointer accent-electricblue"
              />
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                Trigger automated response when CPU usage exceeds this percentage
              </p>
            </div>

            <div className="mb-6">
              <div className="flex items-center justify-between mb-2">
                <label className="block text-sm font-medium">Memory Threshold</label>
                <span className="font-mono text-lg">{data.memoryThreshold}%</span>
              </div>
              <ProgressBar
                value={data.memoryThreshold}
                level={data.memoryThreshold >= 90 ? "critical" : data.memoryThreshold >= 80 ? "warning" : "normal"}
                height={8}
              />
              <input
                type="range"
                min="0"
                max="100"
                value={data.memoryThreshold}
                onChange={(e) => setData({ ...data, memoryThreshold: Number(e.target.value) })}
                className="w-full mt-2 h-2 bg-slate-200 dark:bg-slate-700 rounded-lg appearance-none cursor-pointer accent-warning"
              />
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                Trigger automated response when memory usage exceeds this percentage
              </p>
            </div>

            <div className="space-y-4">
              <Toggle
                label="Auto-shutdown when thresholds exceeded (preference only — not implemented)"
                checked={data.autoShutdown}
                onChange={(e) => setData({ ...data, autoShutdown: e.target.checked })}
                disabled={!data.enabled}
              />
              <Toggle
                label="Aggressive mode (preference only — not implemented)"
                checked={data.aggressiveMode}
                onChange={(e) => setData({ ...data, aggressiveMode: e.target.checked })}
                disabled={!data.enabled}
              />
              <Toggle
                label="Notify on automated action (preference only — not implemented)"
                checked={data.notifyOnAction}
                onChange={(e) => setData({ ...data, notifyOnAction: e.target.checked })}
                disabled={!data.enabled}
              />
            </div>
          </Card>

          <div className="mt-4 flex justify-end gap-3">
            <Button variant="secondary" onClick={handleReset} disabled={saving}>
              Reset to Defaults
            </Button>
            <Button variant="primary" onClick={handleSave} loading={saving}>
              {saved ? "Saved!" : saving ? "Saving…" : "Save Settings"}
            </Button>
          </div>
        </SectionCard>

        {/* Status & History */}
        <SectionCard title="System Status" subtitle="Current adaptive control state (preferences only)">
          <Card className="mb-4">
            <div className="flex items-center justify-between mb-4">
              <div>
                <div className="font-medium">Adaptive Control</div>
                <div className="text-sm text-slate-500 dark:text-slate-400">Overall system status (Panther app policy — no system enforcement)</div>
              </div>
              <Badge
                text={data.enabled ? "Enabled" : "Disabled"}
                status={data.enabled ? "success" : "warning"}
                variant="flat"
              />
            </div>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div className="p-3 rounded-lg bg-slate-950 dark:bg-slate-900">
                <div className="text-slate-500 dark:text-slate-400">CPU Monitor</div>
                <div className="font-mono font-medium">Not implemented</div>
              </div>
              <div className="p-3 rounded-lg bg-slate-950 dark:bg-slate-900">
                <div className="text-slate-500 dark:text-slate-400">Memory Monitor</div>
                <div className="font-mono font-medium">Not implemented</div>
              </div>
              <div className="p-3 rounded-lg bg-slate-950 dark:bg-slate-900">
                <div className="text-slate-500 dark:text-slate-400">Last Action</div>
                <div className="font-mono font-medium">—</div>
              </div>
              <div className="p-3 rounded-lg bg-slate-950 dark:bg-slate-900">
                <div className="text-slate-500 dark:text-slate-400">Actions Taken</div>
                <div className="font-mono font-medium">—</div>
              </div>
            </div>
          </Card>

          <Card className="mb-4">
            <div className="font-medium mb-3">Recent Activity</div>
            <div className="space-y-2 text-sm">
              <p className="text-slate-500 dark:text-slate-400">No automated actions recorded.</p>
              <p className="text-slate-500 dark:text-slate-400">Automatic action execution is not implemented.</p>
            </div>
          </Card>

          <Card>
            <div className="font-medium mb-3">Policy Engine</div>
            <div className="space-y-2 text-sm">
              <div className="flex items-center justify-between p-2 rounded bg-slate-950 dark:bg-slate-900">
                <span>CPU Throttle Policy</span>
                <Badge text="Not implemented" status="info" variant="flat" />
              </div>
              <div className="flex items-center justify-between p-2 rounded bg-slate-950 dark:bg-slate-900">
                <span>Memory Pressure Policy</span>
                <Badge text="Not implemented" status="info" variant="flat" />
              </div>
              <div className="flex items-center justify-between p-2 rounded bg-slate-950 dark:bg-slate-900">
                <span>Thermal Management</span>
                <Badge text="Not implemented" status="info" variant="flat" />
              </div>
            </div>
          </Card>
        </SectionCard>
      </div>
    </PageScaffold>
  );
}