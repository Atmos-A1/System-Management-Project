import { ThemeProvider, useTheme } from "./context/ThemeContext";
import { Dashboard } from "./components/dashboard";

function AppInner() {
  const { theme, setTheme, resolvedTheme } = useTheme();

  return (
    <div className="min-h-screen">
      <Dashboard />
      <div className="fixed bottom-4 right-4 flex items-center gap-2">
        <span className="text-xs text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-slate-800 px-3 py-1 rounded-full">
          {resolvedTheme} mode
        </span>
        <button
          onClick={() =>
            setTheme(theme === "light" ? "dark" : "light")
          }
          className="p-2 rounded-full bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 transition-colors"
          title="Toggle theme"
        >
          {theme === "light" ? "🌙" : "☀️"}
        </button>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <AppInner />
    </ThemeProvider>
  );
}
