// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026  JS8Link contributors

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { en } from "./locales/en";
import { nl } from "./locales/nl";

export type Language = "nl" | "en";
type LanguageContextValue = {
  language: Language;
  setLanguage: (language: Language) => void;
  t: (key: string) => string;
};
const LanguageContext = createContext<LanguageContextValue | null>(null);

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguageState] = useState<Language>(
    () => (localStorage.getItem("js8link-language") as Language) || "nl",
  );
  useEffect(() => {
    void fetch("/api/preferences")
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((preferences: { language?: Language }) => {
        if (preferences.language) {
          localStorage.setItem("js8link-language", preferences.language);
          setLanguageState(preferences.language);
        }
      })
      .catch(() => undefined);
  }, []);
  const setLanguage = (next: Language) => {
    localStorage.setItem("js8link-language", next);
    setLanguageState(next);
    void fetch("/api/preferences", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ language: next }),
    });
  };
  const value = useMemo(
    () => ({
      language,
      setLanguage,
      t: (key: string) => (language === "en" ? en[key] : nl[key]) || key,
    }),
    [language],
  );
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useLanguage() {
  const context = useContext(LanguageContext);
  if (!context) throw new Error("useLanguage must be used inside LanguageProvider");
  return context;
}
