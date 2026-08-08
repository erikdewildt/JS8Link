// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026  JS8Link contributors

export function errorMessage(reason: unknown): string {
  if (reason instanceof Error) return reason.message;
  if (typeof reason === "string") return reason;
  try {
    return JSON.stringify(reason) ?? String(reason);
  } catch {
    return String(reason);
  }
}

export function formatDialFrequency(value?: number | null): string {
  if (value == null || !Number.isFinite(value)) return "--.---.---";
  return Math.round(value)
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, ".");
}

export function formatOffset(value?: number | null): string {
  if (value == null || !Number.isFinite(value)) return "--.---";
  const sign = value >= 0 ? "+" : "−";
  return `${sign}${Math.abs(Math.round(value))
    .toString()
    .padStart(4, "0")
    .replace(/(\d)(\d{3})$/, "$1.$2")}`;
}

export function parseStoredUtc(value: string): Date {
  // SQLite timestamps are stored without an offset and are always UTC.
  return new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(value) ? value : `${value}Z`);
}

export function speedLabel(speed?: number): string {
  if (speed === 0) return "NORMAL";
  if (speed === 1) return "FAST";
  if (speed === 2) return "TURBO";
  if (speed === 4) return "SLOW";
  if (speed === 8) return "JS8 60";
  return "--";
}

export function clampBandScopeMinutes(value: number | string): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 15;
  return Math.min(1440, Math.max(1, Math.round(parsed)));
}

/** Return the rounded mean of known finite SNR values, or null when none exist. */
export function averageSnr(values: Array<number | null | undefined>): number | null {
  const known = values.filter(
    (value): value is number => typeof value === "number" && Number.isFinite(value),
  );
  if (known.length === 0) return null;
  return Math.round((known.reduce((total, value) => total + value, 0) / known.length) * 10) / 10;
}

export function filterStationGraph<
  TStation extends { callsign: string },
  TLink extends { source: string; target: string },
>(
  stations: TStation[],
  links: TLink[],
  callsign: string,
): { stations: TStation[]; links: TLink[] } {
  const selected = callsign.trim().toUpperCase();
  if (!selected) return { stations, links };

  const visibleCallsigns = new Set([selected]);
  const visibleLinks = links.filter((link) => {
    const source = link.source.trim().toUpperCase();
    const target = link.target.trim().toUpperCase();
    const connected = source === selected || target === selected;
    if (connected) {
      visibleCallsigns.add(source);
      visibleCallsigns.add(target);
    }
    return connected;
  });

  return {
    stations: stations.filter((station) =>
      visibleCallsigns.has(station.callsign.trim().toUpperCase()),
    ),
    links: visibleLinks,
  };
}

export function resolveHelpTopicId(
  requested: string,
  available: string[],
  fallback = "global",
): string {
  if (available.includes(requested)) return requested;
  if (available.includes(fallback)) return fallback;
  return available[0] ?? fallback;
}
