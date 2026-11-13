import { useEffect, useState, useCallback, useMemo } from "react";
import { invokeMetric } from "../lib/invoke";
import { useTheme } from "../context/ThemeContext";
import {
  PageScaffold,
  Toolbar,
  SectionCard,
  EmptyState,
  LoadingState,
  ErrorState,
  DataTable,
  FilterBar,
  Badge,
  Button,
} from "../components/shared";

interface Application {
  name: string;
  version: string;
  publisher: string;
  installDate: string | null;
  cpuCores: number | null;
  memoryMb: number | null;
}

function compareVersions(a: string, b: string): number {
  const pa = a.split(".").map(Number);
  const pb = b.split(".").map(Number);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const na = pa[i] || 0;
    const nb = pb[i] || 0;
    if (na !== nb) return nb - na; // Descending
  }
  return 0;
}

export function Applications() {
  const [data, setData] = useState<Application[]>([]);
  const [filteredData, setFilteredData] = useState<Application[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [publisherFilter, setPublisherFilter] = useState("");
  const [sortConfig, setSortConfig] = useState<{ key: keyof Application; direction: "asc" | "desc" }>({
    key: "version",
    direction: "desc",
  });
  const { resolvedTheme } = useTheme();

  const fetchApplications = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const apps = await invokeMetric({
        method: "system_monitor.get_installed_applications",
        params: {},
      });
      setData(apps as Application[]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch installed applications");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchApplications();
  }, [fetchApplications]);

  const publishers = useMemo(() => {
    const pubs = new Set(data.map((a) => a.publisher).filter(Boolean));
    return Array.from(pubs).sort();
  }, [data]);

  useEffect(() => {
    let filtered = [...data];
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      filtered = filtered.filter(
        (a) =>
          (a.name ?? "").toLowerCase().includes(term) ||
          (a.version ?? "").toLowerCase().includes(term) ||
          (a.publisher ?? "").toLowerCase().includes(term)
      );
    }
    if (publisherFilter) {
      filtered = filtered.filter((a) => a.publisher === publisherFilter);
    }
    filtered.sort((a, b) => {
      const aVal = a[sortConfig.key];
      const bVal = b[sortConfig.key];
      if (typeof aVal === "string" && typeof bVal === "string") {
        const cmp = aVal.localeCompare(bVal, undefined, { numeric: true });
        return sortConfig.direction === "asc" ? cmp : -cmp;
      }
      if (typeof aVal === "number" && typeof bVal === "number") {
        return sortConfig.direction === "asc" ? aVal - bVal : bVal - aVal;
      }
      // Handle null values
      if (aVal === null && bVal === null) return 0;
      if (aVal === null) return sortConfig.direction === "asc" ? 1 : -1;
      if (bVal === null) return sortConfig.direction === "asc" ? -1 : 1;
      return 0;
    });
    setFilteredData(filtered);
  }, [data, searchTerm, publisherFilter, sortConfig]);

  const handleSort = (key: keyof Application) => {
    setSortConfig((prev) => ({
      key,
      direction: prev.key === key && prev.direction === "asc" ? "desc" : "asc",
    }));
  };

  const columns = [
    {
      key: "name",
      header: "Name",
      sortable: true,
      render: (row: Application) => (
        <div className="font-medium text-slate-900 dark:text-white">{row.name}</div>
      ),
    },
    {
      key: "version",
      header: "Version",
      sortable: true,
      render: (row: Application) => (
        <div className="font-mono text-slate-600 dark:text-slate-300">{row.version || "—"}</div>
      ),
    },
    {
      key: "publisher",
      header: "Publisher",
      sortable: true,
      render: (row: Application) => (
        <div className="text-slate-500 dark:text-slate-400">{row.publisher || "—"}</div>
      ),
    },
    {
      key: "installDate",
      header: "Install Date",
      sortable: true,
      render: (row: Application) => (
        <div className="text-slate-500 dark:text-slate-400">{row.installDate || "—"}</div>
      ),
    },
    {
      key: "cpuCores",
      header: "CPU Cores",
      sortable: true,
      render: (row: Application) => (
        <div className="font-mono text-slate-600 dark:text-slate-300">{row.cpuCores !== null ? row.cpuCores : "—"}</div>
      ),
    },
    {
      key: "memoryMb",
      header: "Memory (MB)",
      sortable: true,
      render: (row: Application) => (
        <div className="font-mono text-slate-600 dark:text-slate-300">{row.memoryMb !== null ? row.memoryMb.toLocaleString() : "—"}</div>
      ),
    },
  ];

  if (loading) {
    return (
      <PageScaffold title="Applications" subtitle="Installed applications">
        <LoadingState size="md" />
      </PageScaffold>
    );
  }

  if (error) {
    return (
      <PageScaffold title="Applications" subtitle="Installed applications">
        <ErrorState
          title="Error loading applications"
          description={error}
          retryLabel="Retry"
          retryOnClick={fetchApplications}
        />
      </PageScaffold>
    );
  }

  if (data.length === 0) {
    return (
      <PageScaffold title="Applications" subtitle="Installed applications">
        <EmptyState
          icon={<svg className="w-12 h-12 mx-auto text-slate-400 dark:text-slate-500" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
          title="No applications found"
          description={
            typeof window !== "undefined" && navigator.platform?.toLowerCase().includes("win")
              ? "No installed applications were detected."
              : "Application discovery is Windows-only. No data available on this platform."
          }
        />
      </PageScaffold>
    );
  }

  const totalCpuCores = data.reduce((sum, a) => sum + (a.cpuCores ?? 0), 0);
  const totalMemoryMb = data.reduce((sum, a) => sum + (a.memoryMb ?? 0), 0);
  const uniquePublishers = new Set(data.map((a) => a.publisher).filter(Boolean)).size;

  return (
    <PageScaffold title="Applications" subtitle="Installed applications">
      <Toolbar>
        <FilterBar
          placeholder="Search by name, version, or publisher…"
          onSearch={setSearchTerm}
          onFilterChange={setPublisherFilter}
        />
        <select
          value={publisherFilter}
          onChange={(e) => setPublisherFilter(e.target.value)}
          className="w-48 rounded-lg border border-slate-300 dark:border-slate-600 bg-slate-100 dark:bg-slate-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-electricblue"
        >
          <option value="">All Publishers</option>
          {publishers.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </Toolbar>

      <SectionCard title={`Application Inventory (${filteredData.length} of ${data.length})`} subtitle="Installed software with resource profiles">
        <DataTable
          columns={columns}
          data={filteredData}
          keyField="name"
          emptyMessage="No applications match your filter"
          striped
          hoverable
        />
      </SectionCard>

      <SectionCard title="Summary" subtitle="Quick statistics">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="p-4 rounded-lg border bg-slate-950 dark:bg-slate-900 text-center">
            <div className="text-3xl font-bold text-electricblue">{data.length}</div>
            <div className="text-sm text-slate-500 dark:text-slate-400">Total Applications</div>
          </div>
          <div className="p-4 rounded-lg border bg-slate-950 dark:bg-slate-900 text-center">
            <div className="text-3xl font-bold text-violet">{uniquePublishers}</div>
            <div className="text-sm text-slate-500 dark:text-slate-400">Unique Publishers</div>
          </div>
          <div className="p-4 rounded-lg border bg-slate-950 dark:bg-slate-900 text-center">
            <div className="text-3xl font-bold text-warning">{totalCpuCores > 0 ? totalCpuCores : "—"}</div>
            <div className="text-sm text-slate-500 dark:text-slate-400">Total CPU Cores</div>
          </div>
          <div className="p-4 rounded-lg border bg-slate-950 dark:bg-slate-900 text-center">
            <div className="text-3xl font-bold text-healthy">{totalMemoryMb > 0 ? (totalMemoryMb / 1024).toFixed(1) + " GB" : "—"}</div>
            <div className="text-sm text-slate-500 dark:text-slate-400">Total Memory</div>
          </div>
        </div>
      </SectionCard>
    </PageScaffold>
  );
}