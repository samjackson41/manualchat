"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  THEME_STORAGE_KEY,
  storedTheme,
  type Theme,
} from "@/lib/theme";

type ThemeSelection = {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
};

const ThemeContext = createContext<ThemeSelection | null>(null);

export function useTheme(): ThemeSelection {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useTheme must be used inside ThemeProvider");
  }
  return ctx;
}

// The pre-paint script in the layout already applied a theme; read it back.
function appliedTheme(): Theme {
  const stored = storedTheme();
  if (stored) return stored;
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

function applyTheme(theme: Theme) {
  const root = document.documentElement;
  root.classList.toggle("dark", theme === "dark");
  root.style.colorScheme = theme;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  // The server renders the light theme, so the first client render matches the
  // server HTML. The effect below adopts the theme the script applied.
  const [theme, setThemeState] = useState<Theme>("light");

  useEffect(() => {
    setThemeState(appliedTheme());
  }, []);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    applyTheme(next);
    window.localStorage.setItem(THEME_STORAGE_KEY, next);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme(appliedTheme() === "dark" ? "light" : "dark");
  }, [setTheme]);

  const selection = useMemo<ThemeSelection>(
    () => ({ theme, setTheme, toggleTheme }),
    [theme, setTheme, toggleTheme],
  );

  return (
    <ThemeContext.Provider value={selection}>{children}</ThemeContext.Provider>
  );
}
