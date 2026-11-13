import { useEffect, useState, useCallback, useMemo } from "react";
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
  FilterBar,
  Button,
} from "../components/shared";

interface ActivityLog {
  id: number;
  timestamp: string;
  level: "info" | "warning" | "critical";
  message: string;
  component: string;
}

export function ActivityHistory() {
  const [data, setData] = useState<ActivityLog[]>([]);
  const [filteredData, setFilteredData] = useState<ActivityLog[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [levelFilter, setLevelFilter] = useState<"all" | "info" | "warning" | "critical">("all");
  const [searchTerm, setSearchTerm] = useState("");
  const { resolvedTheme } = useTheme();

  const fetchActivity = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const logs = await invokeMetric({
        method: "system_monitor.get_activity_history",
        params: {},
      });
      setData(logs as ActivityLog[]);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to fetch activity history"
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchActivity();
  }, [fetchActivity]);

  useEffect(() => {
    let filtered = [...data];
    if (levelFilter !== "all") {
      filtered = filtered.filter((log) => log.level === levelFilter);
    }
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      filtered = filtered.filter(
        (log) =>
          log.message.toLowerCase().includes(term) ||
          log.component.toLowerCase().includes(term)
      );
    }
    setFilteredData(filtered);
  }, [data, levelFilter, searchTerm]);

  const groupedLogs = useMemo(() => {
    const groups: Record<string, ActivityLog[]> = {};
    filteredData.forEach((log) => {
      const date = new Date(log.timestamp).toLocaleDateString(undefined, {
        year: "numeric",
        month: "long",
        day: "numeric",
      });
      if (!groups[date]) groups[date] = [];
      groups[date].push(log);
    });
    return groups;
  }, [filteredData]);

  const levelConfig = {
    info: { text: "text-slate-400 dark:text-slate-500", bg: "bg-slate-400", label: "Info", badgeStatus: "info" as const },
    warning: { text: "text-warning", bg: "bg-warning", label: "Warning", badgeStatus: "warning" as const },
    critical: { text: "text-critical", bg: "bg-critical", label: "Critical", badgeStatus: "critical" as const },
  };

  const formatTime = (timestamp: string) => {
    return new Date(timestamp).toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  };

  if (loading) {
    return (
      <PageScaffold title="Activity History" subtitle="Recent system events">
        <LoadingState size="md" />
      </PageScaffold>
    );
  }

  if (error) {
    return (
      <PageScaffold title="Activity History" subtitle="Recent system events">
        <ErrorState
          title="Error loading activity history"
          description={error}
          retryLabel="Retry"
          retryOnClick={fetchActivity}
        />
      </PageScaffold>
    );
  }

  if (data.length === 0) {
    return (
      <PageScaffold title="Activity History" subtitle="Recent system events">
        <EmptyState
          icon={<svg className="w-12 h-12 mx-auto text-slate-400 dark:text-slate-500" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
          title="No activity recorded"
          description="No recent system events found. Check back later for activity updates."
        />
      </PageScaffold>
    );
  }

  return (
    <PageScaffold title="Activity History" subtitle="Recent system events">
      <Toolbar>
        <FilterBar
          placeholder="Search events by message or component…"
          onSearch={setSearchTerm}
        />
        <select
          value={levelFilter}
          onChange={(e) => setLevelFilter(e.target.value as "all" | "info" | "warning" | "critical")}
          className="w-40 rounded-lg border border-slate-300 dark:border-slate-600 bg-slate-100 dark:bg-slate-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-electricblue"
        >
          <option value="all">All Levels</option>
          <option value="critical">Critical</option>
          <option value="warning">Warning</option>
          <option value="info">Info</option>
        </select>
        <Badge
          text={`${filteredData.length} events`}
          status={filteredData.some((l) => l.level === "critical") ? "critical" : filteredData.some((l) => l.level === "warning") ? "warning" : "info"}
          variant="flat"
        />
      </Toolbar>

      <SectionCard title={`Activity Log (${filteredData.length} events)`} subtitle="Chronological system events">
        <div className="space-y-6 max-h-[70vh] overflow-y-auto">
          {Object.entries(groupedLogs).map(([date, logs]) => (
            <div key={date} className="space-y-2">
              <div className="flex items-center gap-3">
                <div className="h-px flex-1 border-t border-slate-200 dark:border-slate-800" />
                <span className="px-3 py-1 text-xs font-medium text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-slate-800 rounded-full">
                  {date}
                </span>
                <div className="h-px flex-1 border-t border-slate-200 dark:border-slate-800" />
              </div>
              <div className="space-y-1">
                {logs.map((log) => {
                  const config = levelConfig[log.level];
                  return (
                    <div
                      key={log.id}
                      className="flex items-start gap-3 p-3 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-900/50 transition-colors"
                    >
                      <div className="flex-shrink-0 mt-1.5">
                        <span
                          className={`w-2 h-2 rounded-full ${config.bg}`}
                          title={config.label}
                        />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs text-slate-500 dark:text-slate-400">{formatTime(log.timestamp)}</span>
                          <Badge
                            text={config.label}
                            status={config.badgeStatus}
                            variant="flat"
                          />
                        </div>
                        <p className="mt-1 text-sm text-slate-900 dark:text-white">{log.message}</p>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-xs text-slate-500 dark:text-slate-400 font-mono">{log.component}</span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </SectionCard>

      {filteredData.length !== data.length && (
        <SectionCard title="Filters Applied" subtitle="Active filters">
          <div className="flex flex-wrap gap-2">
            {levelFilter !== "all" && (
              <Badge text={`Level: ${levelFilter}`} status={levelFilter === "critical" ? "critical" : levelFilter === "warning" ? "warning" : "info"} variant="flat" />
            )}
            {searchTerm && <Badge text={`Search: "${searchTerm}"`} status="info" variant="flat" />}
            <Button variant="ghost" size="sm" onClick={() => { setLevelFilter("all"); setSearchTerm(""); }}>
              Clear All Filters
            </Button>
          </div>
        </SectionCard>
      )}
    </PageScaffold>
  );
}