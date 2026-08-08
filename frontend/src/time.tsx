// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026  JS8Link contributors

import { createContext, useContext, useEffect, useMemo, useState } from "react";

export type TimeDisplay = "utc" | "local";

type TimeContextValue = {
  timeDisplay: TimeDisplay;
  setTimeDisplay: (display: TimeDisplay) => void;
  formatTime: (value: string | Date, includeZone?: boolean) => string;
  formatDate: (value: string | Date) => string;
  formatDateTime: (value: string | Date) => string;
  formatUtcClock: (value?: Date) => string;
  formatDisplayClock: (value?: Date) => string;
};

const TimeContext = createContext<TimeContextValue | null>(null);

function asDate(value: string | Date): Date {
  return value instanceof Date
    ? value
    : new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(value) ? value : `${value}Z`);
}

function formatter(display: TimeDisplay, options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  return new Intl.DateTimeFormat(undefined, {
    ...options,
    timeZone: display === "utc" ? "UTC" : undefined,
  });
}

export function TimeProvider({ children }: { children: React.ReactNode }) {
  const [timeDisplay, setTimeDisplayState] = useState<TimeDisplay>(
    () => (localStorage.getItem("js8link-time-display") as TimeDisplay) || "local",
  );

  useEffect(() => {
    void fetch("/api/preferences")
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((preferences: { time_display?: TimeDisplay }) => {
        if (preferences.time_display) {
          localStorage.setItem("js8link-time-display", preferences.time_display);
          setTimeDisplayState(preferences.time_display);
        }
      })
      .catch(() => undefined);
  }, []);

  const setTimeDisplay = (next: TimeDisplay) => {
    localStorage.setItem("js8link-time-display", next);
    setTimeDisplayState(next);
    void fetch("/api/preferences", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ time_display: next }),
    });
  };

  const value = useMemo<TimeContextValue>(() => {
    const timeOptions = (includeZone: boolean): Intl.DateTimeFormatOptions => ({
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
      ...(includeZone ? { timeZoneName: "short" } : {}),
    });
    return {
      timeDisplay,
      setTimeDisplay,
      formatTime: (input, includeZone = true) =>
        formatter(timeDisplay, timeOptions(includeZone)).format(asDate(input)),
      formatDate: (input) =>
        formatter(timeDisplay, { year: "numeric", month: "numeric", day: "numeric" }).format(
          asDate(input),
        ),
      formatDateTime: (input) =>
        formatter(timeDisplay, {
          year: "numeric",
          month: "numeric",
          day: "numeric",
          ...timeOptions(true),
        }).format(asDate(input)),
      formatUtcClock: (input = new Date()) =>
        new Intl.DateTimeFormat(undefined, { ...timeOptions(false), timeZone: "UTC" }).format(
          input,
        ),
      formatDisplayClock: (input = new Date()) =>
        formatter(timeDisplay, timeOptions(true)).format(input),
    };
  }, [timeDisplay]);

  return <TimeContext.Provider value={value}>{children}</TimeContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useTimeDisplay() {
  const context = useContext(TimeContext);
  if (!context) throw new Error("useTimeDisplay must be used inside TimeProvider");
  return context;
}
