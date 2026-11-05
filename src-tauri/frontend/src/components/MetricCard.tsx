import { Activity, Cpu, HardDrive, Battery } from "lucide-react";

interface MetricCardProps {
  title: string;
  subtitle: string;
  value: string;
  detail: string;
}

const ICONS: Record<string, React.ComponentType<React.SVGProps<SVGSVGElement>>> = {
  CPU: Cpu,
  Memory: Activity,
  Storage: HardDrive,
  Battery: Battery,
};

export function MetricCard({
  title,
  subtitle,
  value,
  detail,
}: MetricCardProps) {
  const Icon = ICONS[title] || Cpu;

  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Icon className="w-5 h-5 text-slate-400 dark:text-slate-500" />
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
            {title}
          </h3>
        </div>
        <p className="text-xs text-slate-400 dark:text-slate-500">{subtitle}</p>
      </div>
      <div className="mb-2">
        <p className="text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
          {value}
        </p>
      </div>
      <p className="text-sm text-slate-500 dark:text-slate-400">{detail}</p>
    </div>
  );
}
