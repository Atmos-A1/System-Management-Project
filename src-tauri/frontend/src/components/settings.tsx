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
  Button,
  Card,
  Toggle,
  Select,
} from "../components/shared";

interface SettingsData {
  theme: "light" | "dark" | "system";
  notifications: boolean;
  autoStart: boolean;
  updateCheck: boolean;
  telemetry: boolean;
  compactMode: boolean;
  language: string;
}

export function Settings() {
  const [data, setData] = useState<SettingsData>({
    theme: "system",
    notifications: true,
    autoStart: true,
    updateCheck: true,
    telemetry: false,
    compactMode: false,
    language: "en-US",
  });
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const { theme, setTheme, resolvedTheme } = useTheme();

  const fetchSettings = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const settings = await invokeMetric({
        method: "system_monitor.get_settings",
        params: {},
      });
      const loaded = settings as SettingsData;
      setData(loaded);
      // Sync theme with ThemeContext (ThemeContext is source of truth for UI)
      if (loaded.theme !== theme) {
        setTheme(loaded.theme);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch settings");
      // Fallback to current theme from context
      setData((prev) => ({ ...prev, theme }));
    } finally {
      setLoading(false);
    }
  }, []); // Run once on mount; theme sync is handled by setTheme in saveSettings

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  const saveSettings = useCallback(async (newSettings: SettingsData) => {
    setLoading(true);
    setError(null);
    try {
      // Persist to backend
      await invokeMetric({
        method: "system_monitor.set_settings",
        params: newSettings as unknown as Record<string, unknown>,
      });
      // Apply theme change immediately via ThemeContext
      if (newSettings.theme !== theme) {
        setTheme(newSettings.theme);
      }
      setData(newSettings);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setLoading(false);
    }
  }, [theme, setTheme]);

  const handleThemeChange = (value: "light" | "dark" | "system") => {
    setData((prev) => ({ ...prev, theme: value }));
  };

  const themeOptions = [
    { value: "system", label: "System Default" },
    { value: "light", label: "Light" },
    { value: "dark", label: "Dark" },
  ];

  const languageOptions = [
    { value: "en-US", label: "English (US)" },
    { value: "en-GB", label: "English (UK)" },
    { value: "de-DE", label: "German" },
    { value: "fr-FR", label: "French" },
    { value: "es-ES", label: "Spanish" },
    { value: "ja-JP", label: "Japanese" },
    { value: "zh-CN", label: "Chinese (Simplified)" },
  ];

  if (loading) {
    return (
      <PageScaffold title="Settings" subtitle="Application preferences">
        <LoadingState size="md" />
      </PageScaffold>
    );
  }

  if (error) {
    return (
      <PageScaffold title="Settings" subtitle="Application preferences">
        <ErrorState
          title="Error loading settings"
          description={error}
          retryLabel="Retry"
          retryOnClick={fetchSettings}
        />
      </PageScaffold>
    );
  }

  return (
    <PageScaffold title="Settings" subtitle="Application preferences">
      <Toolbar>
        {saved && (
          <Badge text="Settings saved" status="success" variant="flat" />
        )}
      </Toolbar>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          saveSettings(data);
        }}
        className="space-y-8"
      >
        {/* Appearance Section */}
        <SectionCard title="Appearance" subtitle="Customize how Panther looks">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card>
              <Select
                label="Theme"
                id="theme-select"
                value={data.theme}
                onChange={(e) => handleThemeChange(e.target.value as "light" | "dark" | "system")}
                options={themeOptions}
              />
              <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                System Default follows your OS theme setting. Changes apply on Save.
              </p>
            </Card>

            <Card>
              <Toggle
                label="Compact Mode"
                checked={data.compactMode}
                onChange={(e) => setData((prev) => ({ ...prev, compactMode: e.target.checked }))}
              />
              <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                Reduce spacing and density for more content on screen.
              </p>
            </Card>
          </div>
        </SectionCard>

        {/* General Section */}
        <SectionCard title="General" subtitle="Core application behavior">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card>
              <Toggle
                label="Auto-start on Login"
                checked={data.autoStart}
                onChange={(e) => setData((prev) => ({ ...prev, autoStart: e.target.checked }))}
              />
              <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                Launch Panther automatically when you sign in.
              </p>
            </Card>

            <Card>
              <Toggle
                label="Check for Updates"
                checked={data.updateCheck}
                onChange={(e) => setData((prev) => ({ ...prev, updateCheck: e.target.checked }))}
              />
              <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                Automatically check for new versions on startup.
              </p>
            </Card>

            <Card>
              <Toggle
                label="Notifications"
                checked={data.notifications}
                onChange={(e) => setData((prev) => ({ ...prev, notifications: e.target.checked }))}
              />
              <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                Receive system notifications for critical events.
              </p>
            </Card>

            <Card>
              <Toggle
                label="Anonymous Telemetry"
                checked={data.telemetry}
                onChange={(e) => setData((prev) => ({ ...prev, telemetry: e.target.checked }))}
              />
              <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                Help improve Panther by sending anonymous usage statistics.
              </p>
            </Card>
          </div>
        </SectionCard>

        {/* Language & Regional Section */}
        <SectionCard title="Language & Regional" subtitle="Localization settings">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card>
              <Select
                label="Language"
                id="language-select"
                value={data.language}
                onChange={(e) => setData((prev) => ({ ...prev, language: e.target.value }))}
                options={languageOptions}
              />
            </Card>

            <Card>
              <div className="font-medium mb-2">Region Format</div>
              <p className="text-sm text-slate-500 dark:text-slate-400">
                Uses system regional settings for dates, times, and numbers.
              </p>
            </Card>
          </div>
        </SectionCard>

        {/* Advanced Section */}
        <SectionCard title="Advanced" subtitle="Developer and power user options">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card>
              <div className="font-medium mb-2">Debug Logging</div>
              <Button variant="secondary" size="sm" className="w-full" disabled>
                Open Log Directory
              </Button>
              <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                Access detailed diagnostic logs for troubleshooting.
              </p>
            </Card>

            <Card>
              <div className="font-medium mb-2">Configuration</div>
              <Button variant="secondary" size="sm" className="w-full" disabled>
                Export Settings
              </Button>
              <Button variant="ghost" size="sm" className="w-full mt-2" disabled>
                Import Settings
              </Button>
              <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                Backup or restore your configuration.
              </p>
            </Card>

            <Card>
              <div className="font-medium mb-2 text-critical">Danger Zone</div>
              <Button variant="destructive" size="sm" className="w-full" disabled>
                Reset All Settings
              </Button>
              <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                Restore all settings to their default values. This cannot be undone.
              </p>
            </Card>
          </div>
        </SectionCard>

        {/* About Section */}
        <SectionCard title="About" subtitle="Application information">
          <Card>
            <div className="flex items-center gap-4">
              <div className="w-16 h-16 rounded-xl bg-electricblue dark:bg-violet flex items-center justify-center text-white shadow-lg">
                <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
              <div>
                <h3 className="text-lg font-semibold">Panther System Intelligence</h3>
                <p className="text-sm text-slate-500 dark:text-slate-400">Version 1.0.0</p>
                <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                  Built with Tauri, React, and Rust
                </p>
              </div>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-4 text-sm">
              <div className="p-3 rounded-lg bg-slate-950 dark:bg-slate-900">
                <div className="text-slate-500 dark:text-slate-400">License</div>
                <div className="font-mono">MIT</div>
              </div>
              <div className="p-3 rounded-lg bg-slate-950 dark:bg-slate-900">
                <div className="text-slate-500 dark:text-slate-400">Runtime</div>
                <div className="font-mono">Tauri 2.x</div>
              </div>
              <div className="p-3 rounded-lg bg-slate-950 dark:bg-slate-900">
                <div className="text-slate-500 dark:text-slate-400">Frontend</div>
                <div className="font-mono">React 18 + TypeScript</div>
              </div>
              <div className="p-3 rounded-lg bg-slate-950 dark:bg-slate-900">
                <div className="text-slate-500 dark:text-slate-400">Backend</div>
                <div className="font-mono">Rust + Python sidecar</div>
              </div>
            </div>
          </Card>
        </SectionCard>

        {/* Save/Cancel Actions */}
        <div className="flex justify-end gap-3 pt-4 border-t border-slate-200 dark:border-slate-800">
          <Button type="button" variant="secondary" onClick={fetchSettings} disabled={loading}>
            Reset Form
          </Button>
          <Button type="submit" variant="primary" loading={loading}>
            {saved ? "Saved!" : loading ? "Saving…" : "Save Changes"}
          </Button>
        </div>
      </form>
    </PageScaffold>
  );
}