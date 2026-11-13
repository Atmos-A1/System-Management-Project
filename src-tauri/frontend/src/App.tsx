import { useTheme } from "./context/ThemeContext";
import { useState, createContext, useContext } from "react";
import { Dashboard } from "./components/dashboard";
import { Processes } from "./components/processes";
import { Storage } from "./components/storage";
import { Battery } from "./components/battery";
import { Recommendations } from "./components/recommendations";
import { ActivityHistory } from "./components/activity-history";
import { Settings } from "./components/settings";
import { AdaptiveControl } from "./components/adaptive-control";
import { StartupApps } from "./components/startup-apps";
import { Applications } from "./components/applications";
import { PageScaffold, Toolbar, Badge, ErrorBoundary } from "./components/shared";

/* Nav items match the PRD Part II inventory order.
   Order matters – used by sidebar navigation.
   Per PRD section 7: Overview, Monitor (Processes, Storage, Battery),
   Manage (Adaptive Control, Startup Apps, Applications,
   Recommendations, Activity History), Preferences (Settings). */
const NAV_ITEMS = [
  { name: "Dashboard", icon: "dashboard" },
  { name: "Processes", icon: "processes" },
  { name: "Storage", icon: "storage" },
  { name: "Battery", icon: "battery" },
  { name: "Adaptive Control", icon: "adaptive" },
  { name: "Startup Apps", icon: "startup" },
  { name: "Applications", icon: "applications" },
  { name: "Recommendations", icon: "recommendations" },
  { name: "Activity History", icon: "history" },
  { name: "Settings", icon: "settings" },
];

interface NavContextType {
  currentScreen: string;
  setCurrentScreen: (screen: string) => void;
}

const NavContext = createContext<NavContextType | undefined>(undefined);

function useNav() {
  const ctx = useContext(NavContext);
  if (!ctx) {
    throw new Error("useNav must be used within a NavProvider");
  }
  return ctx;
}

export { useNav };

function Sidebar({ resolvedTheme }: { resolvedTheme: "light" | "dark" }) {
  const { currentScreen, setCurrentScreen } = useNav();
  const isDark = resolvedTheme === "dark";
  return (
    <aside className={`w-64 flex flex-col border-r border-slate-200 dark:border-slate-800 transition-colors duration-300 ${isDark ? "bg-slate-950" : "bg-slate-50"}`}>
      <div className="flex flex-col flex-1 p-4">
        <div className="flex items-center gap-3 mb-8">
          <div className="w-8 h-8 rounded-lg bg-electricblue dark:bg-violet flex items-center justify-center text-white shadow-lg shadow-electricblue/30">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-slate-900 dark:text-white">Panther System Intelligence</h1>
            <p className="text-xs text-slate-500 dark:text-slate-400">System dashboard • {resolvedTheme} mode</p>
          </div>
        </div>
        <nav className="flex-1 space-y-1">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.name}
              onClick={() => setCurrentScreen(item.name)}
              className={`w-full text-left px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                currentScreen === item.name
                  ? "bg-electricblue/10 text-electricblue"
                  : "text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-800"
              }`}
            >
              {item.name}
            </button>
          ))}
        </nav>
      </div>
      <div className="p-4 border-t border-slate-200 dark:border-slate-800">
        <ThemeToggle />
      </div>
    </aside>
  );
}

function ThemeToggle() {
  const { theme, setTheme, resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";
  
  const cycleTheme = () => {
    if (theme === "light") setTheme("dark");
    else if (theme === "dark") setTheme("system");
    else setTheme("light");
  };
  
  const getThemeIcon = () => {
    if (theme === "light") return "☀️";
    if (theme === "dark") return "🌙";
    return "💻";
  };
  
  const getThemeLabel = () => {
    if (theme === "light") return "Light";
    if (theme === "dark") return "Dark";
    return "System";
  };

  return (
    <button
      onClick={cycleTheme}
      className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700"
      title={`Current: ${getThemeLabel()}. Click to cycle.`}
    >
      <span className="text-lg">{getThemeIcon()}</span>
      <span>{getThemeLabel()}</span>
      <span className="ml-auto text-xs text-slate-400 dark:text-slate-500">Theme</span>
    </button>
  );
}

export default function App() {
  const { theme, setTheme, resolvedTheme } = useTheme();
  const [currentScreen, setCurrentScreen] = useState("Dashboard");

  const screenComponents: Record<string, React.ComponentType> = {
    Dashboard,
    Processes,
    Storage,
    Battery,
    "Adaptive Control": AdaptiveControl,
    "Startup Apps": StartupApps,
    Applications,
    Recommendations,
    "Activity History": ActivityHistory,
    Settings,
  };

  const CurrentScreen = screenComponents[currentScreen] || Dashboard;

  return (
    <NavContext.Provider value={{ currentScreen, setCurrentScreen }}>
      <PageScaffold
        title="Panther System Intelligence"
        subtitle="System dashboard"
      >
        <div className="flex min-h-screen">
          <Sidebar resolvedTheme={resolvedTheme} />
          <main className="flex-1 flex flex-col min-w-0">
            <Toolbar alignRight>
              <Badge text="Online" status="success" variant="flat" />
            </Toolbar>
            <div className="flex-1 p-6 overflow-y-auto">
              <ErrorBoundary>
                <CurrentScreen />
              </ErrorBoundary>
            </div>
          </main>
        </div>
      </PageScaffold>
    </NavContext.Provider>
  );
}