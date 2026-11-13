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
  DataTable,
  ColumnDef,
  Button,
  Toggle,
  Card,
} from "../components/shared";

interface StartupApp {
  name: string;
  executable: string;
  isEnabled: boolean;
  cpuImpact: number | null;
  memoryImpact: number | null;
}

export function StartupApps() {
  const [data, setData] = useState<StartupApp[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const { resolvedTheme } = useTheme();

  const fetchStartupApps = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const apps = await invokeMetric({
        method: "system_monitor.get_startup_apps",
        params: {},
      });
      setData(apps as StartupApp[]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch startup apps");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStartupApps();
  }, [fetchStartupApps]);

  const handleToggle = async (executable: string, newState: boolean) => {
    // Optimistic update
    setData((prev) =>
      prev.map((app) =>
        app.executable === executable ? { ...app, isEnabled: newState } : app
      )
    );
    setActionError(null);
    try {
      await invokeMetric({
        method: "system_monitor.set_startup_app_state",
        params: { executable, enabled: newState },
      });
    } catch (err) {
      // Revert on error
      setData((prev) =>
        prev.map((app) =>
          app.executable === executable ? { ...app, isEnabled: !newState } : app
        )
      );
      const message = err instanceof Error ? err.message : "Failed to update startup app";
      setActionError(message);
      console.error("Failed to update startup app:", err);
    }
  };

  const getImpactLevel = (value: number | null): "normal" | "warning" | "critical" => {
    if (value === null) return "normal";
    if (value >= 85) return "critical";
    if (value >= 65) return "warning";
    return "normal";
  };

  const columns: ColumnDef<StartupApp & { enabled: string }>[] = [
    { key: "name", header: "Application", width: "240px" },
    { key: "enabled", header: "Status", width: "100px" },
    {
      key: "cpuImpact",
      header: "CPU Impact",
      width: "160px",
      render: (row) => {
        const value = row.cpuImpact;
        if (value === null) return <span className="text-slate-400 dark:text-slate-500">—</span>;
        const level = getImpactLevel(value);
        return (
          <span className={`font-mono ${level === "critical" ? "text-critical" : level === "warning" ? "text-warning" : "text-healthy"}`}>
            {value.toFixed(1)}%
          </span>
        );
      },
    },
    {
      key: "memoryImpact",
      header: "Memory Impact",
      width: "160px",
      render: (row) => {
        const value = row.memoryImpact;
        if (value === null) return <span className="text-slate-400 dark:text-slate-500">—</span>;
        const level = getImpactLevel(value);
        return (
          <span className={`font-mono ${level === "critical" ? "text-critical" : level === "warning" ? "text-warning" : "text-healthy"}`}>
            {value.toFixed(1)}%
          </span>
        );
      },
    },
    {
      key: "actions",
      header: "Actions",
      width: "120px",
      render: (row) => (
        <Toggle
          checked={row.isEnabled}
          onChange={(e) => handleToggle(row.executable, e.target.checked)}
        />
      ),
    },
  ];

  const tableData = data.map((app) => ({
    ...app,
    enabled: app.isEnabled ? "Enabled" : "Disabled",
  }));

  if (loading) {
    return (
      <PageScaffold title="Startup Apps" subtitle="Applications that launch at startup">
        <LoadingState size="md" />
      </PageScaffold>
    );
  }

  if (error) {
    return (
      <PageScaffold title="Startup Apps" subtitle="Applications that launch at startup">
        <ErrorState
          title="Error loading startup apps"
          description={error}
          retryLabel="Retry"
          retryOnClick={fetchStartupApps}
        />
      </PageScaffold>
    );
  }

  if (data.length === 0) {
    return (
      <PageScaffold title="Startup Apps" subtitle="Applications that launch at startup">
        <EmptyState
          icon={<svg className="w-12 h-12 mx-auto text-slate-400 dark:text-slate-500" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-8l-2 2z" /></svg>}
          title="No startup apps"
          description="No applications are configured to launch at startup."
        />
      </PageScaffold>
    );
  }

  const enabledCount = data.filter((a) => a.isEnabled).length;
  const totalCpuImpact = data.reduce((sum, a) => sum + (a.cpuImpact ?? 0), 0);
  const totalMemoryImpact = data.reduce((sum, a) => sum + (a.memoryImpact ?? 0), 0);

  return (
    <PageScaffold title="Startup Apps" subtitle="Applications that launch at startup">
      <Toolbar>
        <span className="text-sm text-slate-500 dark:text-slate-400">
          {enabledCount} of {data.length} enabled
        </span>
        {actionError && (
          <span className="ml-4 text-sm text-critical flex items-center gap-1">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
            {actionError}
          </span>
        )}
      </Toolbar>

      <SectionCard title="Startup Applications" subtitle="Manage which applications launch automatically">
        <DataTable
          columns={columns}
          data={tableData}
          keyField="executable"
          emptyMessage="No startup applications found"
          striped
          hoverable
          onRowClick={(row) => {
            // Could open inspector drawer here
          }}
        />
      </SectionCard>

      <SectionCard title="Impact Summary" subtitle="Estimated resource impact of startup items">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Card>
            <div className="font-medium mb-3">Total CPU Impact at Startup</div>
            <ProgressBar
              value={totalCpuImpact}
              level={getImpactLevel(totalCpuImpact || null)}
              height={12}
              showLabel
              label={totalCpuImpact > 0 ? `${totalCpuImpact.toFixed(1)}%` : "—"}
            />
            <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
              Combined CPU usage from all enabled startup apps
            </p>
          </Card>
          <Card>
            <div className="font-medium mb-3">Total Memory Impact at Startup</div>
            <ProgressBar
              value={Math.min(100, totalMemoryImpact / 2)}
              level={getImpactLevel(totalMemoryImpact > 0 ? Math.min(100, totalMemoryImpact / 2) : null)}
              height={12}
              showLabel
              label={totalMemoryImpact > 0 ? `${totalMemoryImpact.toFixed(1)}%` : "—"}
            />
            <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
              Combined memory usage from all enabled startup apps
            </p>
          </Card>
        </div>
      </SectionCard>
    </PageScaffold>
  );
}