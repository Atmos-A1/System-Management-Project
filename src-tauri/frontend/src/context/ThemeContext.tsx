import { createContext, useContext, useEffect, useState } from "react";

type Theme = "light" | "dark" | "system";

interface ThemeContextType {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  resolvedTheme: "light" | "dark";
  setCurrentScreen?: (screen: string) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return ctx;
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>("dark");
  const [resolvedTheme, setResolvedTheme] = useState<"light" | "dark">("dark");

  useEffect(() => {
    const root = window.document.documentElement;
    const resolve = (t: Theme) => {
      if (t === "system") {
        const system = window.matchMedia("(prefers-color-scheme: dark)").matches
          ? "dark"
          : "light";
        root.classList.toggle("dark", system === "dark");
        root.setAttribute("data-theme", system);
        return system;
      }
      if (t === "dark") {
        root.classList.add("dark");
        root.setAttribute("data-theme", "dark");
        return "dark";
      }
      // t === "light"
      root.classList.remove("dark");
      root.setAttribute("data-theme", "light");
      return "light";
    };

    const resolved = resolve(theme);
    setResolvedTheme(resolved);

    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => {
      if (theme === "system") {
        const resolved = resolve("system");
        setResolvedTheme(resolved);
      }
    };
    media.addEventListener("change", handler);
    return () => media.removeEventListener("change", handler);
  }, [theme]);

  return (
    <ThemeContext.Provider value={{ theme, setTheme, resolvedTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}
