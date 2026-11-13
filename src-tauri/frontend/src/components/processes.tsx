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
  FilterBar,
  DataTable,
  ProgressBar,
  Button,
} from "../components/shared";

interface ProcessInfo {
  pid: number;
  name: string;
  cpu: number;
  memory: number;
  status: "running" | "sleeping" | "stopped";
}

export function Processes() {
  const [data, setData] = useState<ProcessInfo[]>([]);
  const [filteredData, setFilteredData] = useState<ProcessInfo[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [selectedProcess, setSelectedProcess] = useState<ProcessInfo | null>(null);
  const { resolvedTheme } = useTheme();

  const fetchProcesses = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const processes = await invokeMetric({
        method: "system_monitor.get_processes",
        params: {},
      });
      const typed = processes as ProcessInfo[];
      setData(typed);
      setFilteredData(typed);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to fetch processes"
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProcesses();
  }, [fetchProcesses]);

  useEffect(() => {
    let filtered = data;
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      filtered = filtered.filter(
        (p) => p.name.toLowerCase().includes(term) || String(p.pid).includes(term)
      );
    }
    if (statusFilter) {
      filtered = filtered.filter((p) => p.status === statusFilter);
    }
    setFilteredData(filtered);
  }, [data, searchTerm, statusFilter]);

  const getProgressLevel = (cpu: number): "normal" | "warning" | "critical" => {
    if (cpu >= 85) return "critical";
    if (cpu >= 65) return "warning";
    return "normal";
  };

  const columns = [
    { key: "name", header: "Name", width: "280px" },
    { key: "pid", header: "PID", width: "80px" },
    { key: "cpu", header: "CPU %", width: "140px" },
    { key: "memory", header: "Memory", width: "120px" },
    { key: "status", header: "Status", width: "120px" },
  ];

  if (loading) {
    return (
      <PageScaffold title="Processes" subtitle="Running processes">
        <LoadingState size="md" />
      </PageScaffold>
    );
  }

  if (error) {
    return (
      <PageScaffold title="Processes" subtitle="Running processes">
        <ErrorState
          title="Error loading processes"
          description={error}
          retryLabel="Retry"
          retryOnClick={fetchProcesses}
        />
      </PageScaffold>
    );
  }

  return (
    <PageScaffold title="Processes" subtitle="Running processes">
      <Toolbar>
        <FilterBar
          placeholder="Search processes by name or PID…"
          onSearch={setSearchTerm}
          onFilterChange={setStatusFilter}
        />
      </Toolbar>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        <SectionCard title="Process List" subtitle={`${filteredData.length} of ${data.length} processes`}>
          <DataTable
            columns={columns}
            data={filteredData}
            keyField="pid"
            emptyMessage="No processes match your filter"
            onRowClick={setSelectedProcess}
            striped
            hoverable
          />
        </SectionCard>

        <SectionCard title="Process Inspector" subtitle={selectedProcess ? selectedProcess.name : "Select a process"}>
          {selectedProcess ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <div className="text-slate-500 dark:text-slate-400">PID</div>
                  <div className="font-mono font-medium">{selectedProcess.pid}</div>
                </div>
                <div>
                  <div className="text-slate-500 dark:text-slate-400">Status</div>
                  <Badge
                    status={
                      selectedProcess.status === "running"
                        ? "success"
                        : selectedProcess.status === "sleeping"
                        ? "info"
                        : "warning"
                    }
                    text={
                      selectedProcess.status.charAt(0).toUpperCase() +
                      selectedProcess.status.slice(1)
                    }
                    variant="flat"
                  />
                </div>
                <div>
                  <div className="text-slate-500 dark:text-slate-400">CPU Usage</div>
                  <div className="font-mono font-medium">{selectedProcess.cpu.toFixed(1)}%</div>
                </div>
                <div>
                  <div className="text-slate-500 dark:text-slate-400">Memory</div>
                  <div className="font-mono font-medium">{selectedProcess.memory.toFixed(1)} GB</div>
                </div>
              </div>

              <div>
                <div className="text-sm font-medium mb-2">CPU Utilization</div>
                <ProgressBar
                  value={selectedProcess.cpu}
                  level={getProgressLevel(selectedProcess.cpu)}
                  height={10}
                  showLabel
                />
              </div>

              <div>
                <div className="text-sm font-medium mb-2">Memory Utilization</div>
                <ProgressBar
                  value={selectedProcess.memory > 0 ? Math.min(100, (selectedProcess.memory / 32) * 100) : 0}
                  level="normal"
                  height={10}
                  showLabel
                  label={`${selectedProcess.memory.toFixed(1)} GB`}
                />
              </div>

              <div className="pt-2 border-t border-slate-200 dark:border-slate-800">
                <Button variant="secondary" className="w-full" disabled>
                  View Details
                </Button>
                <Button variant="destructive" className="w-full mt-2" disabled>
                  End Process
                </Button>
              </div>
            </div>
          ) : (
            <EmptyState
              icon={<svg className="w-12 h-12 mx-auto text-slate-400 dark:text-slate-500" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
              title="No process selected"
              description="Click a process in the list to view detailed information and actions."
            />
          )}
        </SectionCard>
      </div>
    </PageScaffold>
  );
}