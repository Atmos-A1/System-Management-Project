import { useEffect, useState, useCallback } from "react";
import { invokeMetric } from "../lib/invoke";
import { useTheme } from "../context/ThemeContext";
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
  Card,
} from "../components/shared";

interface StorageInfo {
  total: number;
  used: number;
  free: number;
  percent: number;
  paths?: string[];
}

interface DirectoryEntry {
  name: string;
  path: string;
  type: "directory" | "file" | "link" | "reparse" | "other";
  size: number | null;
  modified: string | null;
  is_dir: boolean;
  is_file: boolean;
  is_link: boolean;
  is_reparse: boolean;
  is_hidden: boolean;
  error?: string;
}

interface DirectoryListing {
  path: string;
  entries: DirectoryEntry[];
  errors: Array<{ path: string; error: string; kind: string }>;
  truncated: boolean;
  limit: number;
  cancelled: boolean;
  error: string | null;
}

export function Storage() {
  const [data, setData] = useState<StorageInfo | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedPath, setSelectedPath] = useState<string>(
    typeof window !== "undefined" && navigator.platform?.toLowerCase().includes("win") ? "C:\\" : "/"
  );
  const [dirListing, setDirListing] = useState<DirectoryListing | null>(null);
  const [dirLoading, setDirLoading] = useState(false);
  const [dirError, setDirError] = useState<string | null>(null);
  const { resolvedTheme } = useTheme();

  const fetchStorage = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const storage = await invokeMetric({
        method: "system_monitor.get_disk_usage",
        params: {},
      });
      setData(storage as StorageInfo);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch storage info");
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchDirectory = useCallback(async (path?: string) => {
    setDirLoading(true);
    setDirError(null);
    try {
      const params = path ? { path } : {};
      const result = await invokeMetric({
        method: "system_monitor.list_directory",
        params,
      });
      const listing = result as DirectoryListing;
      setDirListing(listing);
      setSelectedPath(listing.path);
    } catch (err) {
      setDirError(err instanceof Error ? err.message : "Failed to list directory");
      setDirListing(null);
    } finally {
      setDirLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStorage();
    fetchDirectory(); // No path = platform-aware default
  }, [fetchStorage, fetchDirectory]);

  if (loading) {
    return (
      <PageScaffold title="Storage" subtitle="Disk usage and analysis">
        <LoadingState size="md" />
      </PageScaffold>
    );
  }

  if (error) {
    return (
      <PageScaffold title="Storage" subtitle="Disk usage and analysis">
        <ErrorState
          title="Error loading storage"
          description={error}
          retryLabel="Retry"
          retryOnClick={fetchStorage}
        />
      </PageScaffold>
    );
  }

  if (!data) {
    return (
      <PageScaffold title="Storage" subtitle="Disk usage and analysis">
        <EmptyState
          icon={<svg className="w-12 h-12 mx-auto text-slate-400 dark:text-slate-500" viewBox="0 0 24 24" fill="none" stroke="currentColor"><rect x="3" y="3" width="18" height="18" rx="2" ry="2" /><circle cx="8.5" cy="8.5" r="5.5" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M21 21l-6-6m0-6l-6 6" /></svg>}
          title="No storage data"
          description="Unable to retrieve disk usage information."
        />
      </PageScaffold>
    );
  }

  const totalGB = (data.total / 1024 / 1024 / 1024).toFixed(1);
  const usedGB = (data.used / 1024 / 1024 / 1024).toFixed(1);
  const freeGB = (data.free / 1024 / 1024 / 1024).toFixed(1);
  const percent = data.percent;

  const getLevel = (p: number): "normal" | "warning" | "critical" => {
    if (p >= 85) return "critical";
    if (p >= 65) return "warning";
    return "normal";
  };

  const level = getLevel(percent);
  const levelLabel = level === "critical" ? "Critical" : level === "warning" ? "Warning" : "Healthy";

  const formatSize = (bytes: number | null) => {
    if (bytes === null) return "—";
    const gb = bytes / 1024 / 1024 / 1024;
    return gb >= 1 ? `${gb.toFixed(1)} GB` : `${(bytes / 1024 / 1024).toFixed(0)} MB`;
  };

  const getParentPath = (path: string): string => {
    // Handle both Unix and Windows paths
    if (path === "/" || path === "C:\\" || path.match(/^[A-Za-z]:\\?$/)) {
      return path;
    }
    // Normalize separators
    const isWindows = path.includes("\\");
    const sep = isWindows ? "\\" : "/";
    const parts = path.split(sep).filter(Boolean);
    if (parts.length <= 1) {
      return isWindows ? "C:\\" : "/";
    }
    return (isWindows ? "" : "/") + parts.slice(0, -1).join(sep) + (isWindows ? "\\" : "");
  };

  const handleEntryClick = (entry: DirectoryEntry) => {
    if (entry.is_dir) {
      fetchDirectory(entry.path);
    }
  };

  const handleParentClick = () => {
    const parent = getParentPath(selectedPath);
    if (parent !== selectedPath) {
      fetchDirectory(parent);
    }
  };

  return (
    <PageScaffold title="Storage" subtitle="Disk usage and analysis">
      <Toolbar>
        <Badge text={levelLabel} status={level === "critical" ? "critical" : level === "warning" ? "warning" : "success"} variant="flat" />
        <span className="ml-4 text-sm text-slate-500 dark:text-slate-400">
          {usedGB} GB of {totalGB} GB used
        </span>
        <Button variant="secondary" size="sm" onClick={() => fetchDirectory(selectedPath)} disabled={dirLoading}>
          {dirLoading ? "Refreshing…" : "Refresh"}
        </Button>
      </Toolbar>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Overview cards */}
        <div className="lg:col-span-1 space-y-4">
          <SectionCard title="Overview" subtitle="Disk capacity">
            <div className="grid grid-cols-2 gap-4">
              <div className="p-4 rounded-lg border bg-slate-950 dark:bg-slate-900 text-white">
                <div className="text-3xl font-bold">{usedGB} GB</div>
                <div className="text-slate-400">Used</div>
              </div>
              <div className="p-4 rounded-lg border bg-slate-950 dark:bg-slate-900 text-white">
                <div className="text-3xl font-bold">{freeGB} GB</div>
                <div className="text-slate-400">Free</div>
              </div>
            </div>
            <ProgressBar value={percent} level={level} height={10} showLabel label={`${percent}% used`} />
            <div className="mt-2 grid grid-cols-2 gap-4 text-sm">
              <div>
                <div className="font-medium text-slate-600 dark:text-slate-300">Total</div>
                <div className="font-mono text-slate-900 dark:text-white">{totalGB} GB</div>
              </div>
              <div>
                <div className="font-medium text-slate-600 dark:text-slate-300">Available</div>
                <div className="font-mono text-slate-900 dark:text-white">{freeGB} GB</div>
              </div>
            </div>
          </SectionCard>

          <SectionCard title="Quick Actions">
            <div className="space-y-2">
              <Button variant="secondary" className="w-full" disabled>
                Cleanup Recommendations
              </Button>
              <Button variant="secondary" className="w-full" disabled>
                Duplicate Finder
              </Button>
              <Button variant="ghost" className="w-full" disabled>
                Partition Manager
              </Button>
            </div>
          </SectionCard>
        </div>

        {/* Directory Explorer */}
        <SectionCard title="Directory Explorer" subtitle={selectedPath} className="lg:col-span-2">
          <div className="mb-4 flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={handleParentClick} disabled={selectedPath === "/" || selectedPath === "C:\\"}>
              ← Parent
            </Button>
            <span className="text-sm text-slate-500 dark:text-slate-400 font-mono">{selectedPath}</span>
          </div>

          {dirLoading ? (
            <div className="flex items-center justify-center h-64">
              <LoadingState size="md" />
            </div>
          ) : dirError ? (
            <ErrorState
              title="Error loading directory"
              description={dirError}
              retryLabel="Retry"
              retryOnClick={() => fetchDirectory(selectedPath)}
            />
          ) : dirListing ? (
            <div className="overflow-x-auto">
              {dirListing.error && (
                <div className="mb-4 p-4 rounded-lg bg-critical/10 border border-critical/20">
                  <div className="flex items-center gap-2 text-critical">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
                    <span className="text-sm font-medium">Directory access error:</span>
                    <span className="text-sm">{dirListing.error}</span>
                  </div>
                </div>
              )}
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200 dark:border-slate-800">
                    <th className="text-left p-3 font-semibold">Name</th>
                    <th className="text-left p-3 font-semibold">Size</th>
                    <th className="text-left p-3 font-semibold">Type</th>
                    <th className="text-left p-3 font-semibold">Modified</th>
                  </tr>
                </thead>
                <tbody>
                  {dirListing.entries.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="p-6 text-center text-slate-500 dark:text-slate-400">
                        {dirListing.error
                          ? "No entries accessible (see error above)"
                          : "No entries found"}
                      </td>
                    </tr>
                  ) : (
                    dirListing.entries.map((entry) => (
                      <tr
                        key={entry.path}
                        className="border-b border-slate-200/50 dark:border-slate-800/50 hover:bg-slate-50 dark:hover:bg-slate-900/50 cursor-pointer"
                        onClick={() => handleEntryClick(entry)}
                      >
                        <td className="p-3 font-medium flex items-center gap-2">
                          {entry.is_dir && <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" /></svg>}
                          {entry.is_file && <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" /></svg>}
                          {entry.is_link && <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" /></svg>}
                          {entry.is_reparse && <svg className="w-4 h-4 text-warning" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M12 9v3m0 0v3m0-3h3m-3 0H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
                          {entry.is_hidden && <span className="text-xs text-slate-400 dark:text-slate-500">(hidden)</span>}
                          {entry.name}
                        </td>
                        <td className="p-3 font-mono text-slate-600 dark:text-slate-300">{formatSize(entry.size)}</td>
                        <td className="p-3">
                          <Badge
                            text={entry.type}
                            status={entry.is_dir ? "info" : entry.is_file ? "success" : entry.is_link ? "warning" : entry.is_reparse ? "critical" : "info"}
                            variant="flat"
                          />
                        </td>
                        <td className="p-3 text-slate-500 dark:text-slate-400 font-mono">{entry.modified || "—"}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-64 text-slate-500 dark:text-slate-400">
              <svg className="w-12 h-12 mb-3" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 9h6v6H9z" />
              </svg>
              <p>No directory data available</p>
            </div>
          )}

          {dirListing?.truncated && (
            <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
              Listing truncated to {dirListing.limit} entries.
            </p>
          )}
          {dirListing?.errors && dirListing.errors.length > 0 && (
            <p className="mt-2 text-xs text-warning">
              {dirListing.errors.length} entr{'y' + (dirListing.errors.length !== 1 ? 'ies' : '')} could not be read (permission/missing).
            </p>
          )}
        </SectionCard>
      </div>

      <p className="mt-4 text-sm text-slate-500 dark:text-slate-400 text-center">
        Advanced features: cleanup review, duplicate detection, and partition management coming soon.
      </p>
    </PageScaffold>
  );
}