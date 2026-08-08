// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026  JS8Link contributors

import { createContext, useContext, useEffect, useState } from "react";

export type Theme = "dark" | "light" | "forest" | "field-light" | "high-contrast";
type ThemeContextValue = { theme: Theme; setTheme: (theme: Theme) => void };
const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(
    () => (localStorage.getItem("js8link-theme") as Theme) || "dark",
  );
  useEffect(() => {
    void fetch("/api/preferences")
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((preferences: { theme?: Theme }) => {
        if (preferences.theme) {
          localStorage.setItem("js8link-theme", preferences.theme);
          setThemeState(preferences.theme);
        }
      })
      .catch(() => undefined);
  }, []);
  const setTheme = (next: Theme) => {
    localStorage.setItem("js8link-theme", next);
    setThemeState(next);
    void fetch("/api/preferences", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ theme: next }),
    });
  };
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  return <ThemeContext.Provider value={{ theme, setTheme }}>{children}</ThemeContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("useTheme must be used inside ThemeProvider");
  return context;
}
