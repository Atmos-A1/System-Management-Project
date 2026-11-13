import { useEffect, useState, useCallback } from "react";
import { invokeMetric } from "../lib/invoke";
import { useTheme } from "../context/ThemeContext";
import { useNav } from "../App";
import {
  PageScaffold,
  Toolbar,
  Badge,
  SectionCard,
  EmptyState,
  LoadingState,
  ErrorState,
  Button,
  Card,
} from "../components/shared";

interface Recommendation {
  id: string;
  title: string;
  description: string;
  action?: string;
  actionTarget?: string; // Screen to navigate to
  level: "normal" | "warning" | "critical";
  category: "performance" | "storage" | "battery" | "startup" | "security";
}

export function Recommendations() {
  const [data, setData] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const { resolvedTheme } = useTheme();
  const { setCurrentScreen } = useNav();

  const fetchRecommendations = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const recs = await invokeMetric({
        method: "system_monitor.get_recommendations",
        params: {},
      });
      setData(recs as Recommendation[]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch recommendations");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRecommendations();
  }, [fetchRecommendations]);

  const getLevelConfig = (level: string) => {
    switch (level) {
      case "critical":
        return { bg: "bg-critical/10", border: "border-critical", text: "text-critical", badgeStatus: "critical" as const };
      case "warning":
        return { bg: "bg-warning/10", border: "border-warning", text: "text-warning", badgeStatus: "warning" as const };
      default:
        return { bg: "bg-healthy/10", border: "border-healthy", text: "text-healthy", badgeStatus: "success" as const };
    }
  };

  const getCategoryIcon = (category: string) => {
    switch (category) {
      case "performance":
        return "⚡";
      case "storage":
        return "💾";
      case "battery":
        return "🔋";
      case "startup":
        return "🚀";
      case "security":
        return "🔒";
      default:
        return "📋";
    }
  };

  const handleAction = (rec: Recommendation) => {
    if (rec.actionTarget && setCurrentScreen) {
      setCurrentScreen(rec.actionTarget);
    } else if (rec.action) {
      window.alert(`Action: ${rec.action}`);
    }
  };

  if (loading) {
    return (
      <PageScaffold title="Recommendations" subtitle="Actionable, explainable recommendations">
        <LoadingState size="md" />
      </PageScaffold>
    );
  }

  if (error) {
    return (
      <PageScaffold title="Recommendations" subtitle="Actionable, explainable recommendations">
        <ErrorState
          title="Error loading recommendations"
          description={error}
          retryLabel="Retry"
          retryOnClick={fetchRecommendations}
        />
      </PageScaffold>
    );
  }

  if (data.length === 0) {
    return (
      <PageScaffold title="Recommendations" subtitle="Actionable, explainable recommendations">
        <EmptyState
          icon={<svg className="w-12 h-12 mx-auto text-slate-400 dark:text-slate-500" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>}
          title="No recommendations at this time"
          description="All system metrics are within normal operating parameters."
        />
      </PageScaffold>
    );
  }

  // Group by level: critical first, then warning, then normal
  const sorted = [...data].sort((a, b) => {
    const order = { critical: 0, warning: 1, normal: 2 };
    return order[a.level] - order[b.level];
  });

  return (
    <PageScaffold title="Recommendations" subtitle="Actionable, explainable recommendations">
      <Toolbar>
        <span className="text-sm text-slate-500 dark:text-slate-400">
          {data.filter((r) => r.level === "critical").length} critical, {data.filter((r) => r.level === "warning").length} warnings
        </span>
      </Toolbar>

      <div className="space-y-4">
        {sorted.map((rec) => {
          const config = getLevelConfig(rec.level);
          return (
            <Card key={rec.id} className={`${config.bg} ${config.border}`}>
              <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
                <div className="flex-1">
                  <div className="flex items-start gap-3">
                    <span className="text-2xl mt-1">{getCategoryIcon(rec.category)}</span>
                    <div>
                      <div className="flex items-center gap-2">
                        <h4 className="font-medium text-slate-900 dark:text-white">{rec.title}</h4>
                        <Badge
                          status={config.badgeStatus}
                          text={rec.level.charAt(0).toUpperCase() + rec.level.slice(1)}
                          variant="flat"
                        />
                      </div>
                      <p className={`mt-1 text-sm ${config.text}`}>{rec.description}</p>
                    </div>
                  </div>
                </div>
                {rec.action && (
                  <Button
                    variant="primary"
                    size="sm"
                    className="md:w-auto"
                    onClick={() => handleAction(rec)}
                  >
                    Take Action
                  </Button>
                )}
              </div>
            </Card>
          );
        })}
      </div>

      <SectionCard title="Recommendation Engine" subtitle="How recommendations are generated">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card>
            <div className="font-medium mb-2">Performance Analysis</div>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Monitors CPU, memory, and I/O patterns to identify bottlenecks and resource contention.
            </p>
          </Card>
          <Card>
            <div className="font-medium mb-2">Storage Optimization</div>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Analyzes disk usage, duplicate files, and cleanup opportunities to reclaim space.
            </p>
          </Card>
          <Card>
            <div className="font-medium mb-2">Battery & Power</div>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Evaluates power consumption patterns and suggests settings for optimal battery life.
            </p>
          </Card>
        </div>
      </SectionCard>
    </PageScaffold>
  );
}