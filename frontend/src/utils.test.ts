// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026  JS8Link contributors

import { describe, expect, it } from "vitest";
import {
  errorMessage,
  averageSnr,
  clampBandScopeMinutes,
  formatDialFrequency,
  formatOffset,
  filterStationGraph,
  parseStoredUtc,
  speedLabel,
  resolveHelpTopicId,
} from "./utils";

describe("help context resolution", () => {
  it("keeps a known context", () => {
    expect(resolveHelpTopicId("monitor", ["global", "monitor"])).toBe("monitor");
  });

  it("falls back to the global topic for unknown contexts", () => {
    expect(resolveHelpTopicId("radio", ["global", "chat"])).toBe("global");
  });
});

describe("radio display helpers", () => {
  it("limits the bandscope to one day", () => {
    expect(clampBandScopeMinutes(1441)).toBe(1440);
    expect(clampBandScopeMinutes(0)).toBe(1);
    expect(clampBandScopeMinutes("invalid")).toBe(15);
  });
  it.each([
    [14074000, "14.074.000"],
    [7078000.4, "7.078.000"],
    [null, "--.---.---"],
    [Number.NaN, "--.---.---"],
  ])("formats dial frequency %s", (value, expected) => {
    expect(formatDialFrequency(value)).toBe(expected);
  });

  it.each([
    [1500, "+1.500"],
    [-15, "−0.015"],
    [undefined, "--.---"],
    [null, "--.---"],
    [Number.NaN, "--.---"],
  ])("formats offset %s", (value, expected) => {
    expect(formatOffset(value)).toBe(expected);
  });

  it.each([
    [0, "NORMAL"],
    [1, "FAST"],
    [2, "TURBO"],
    [4, "SLOW"],
    [8, "JS8 60"],
    [99, "--"],
  ])("maps speed %s", (value, expected) => {
    expect(speedLabel(value)).toBe(expected);
  });
});

describe("station graph filtering", () => {
  const stations = ["PE1PUX", "PD3V", "LA7HKA", "OZ9JEP", "N0CALL"].map((callsign) => ({
    callsign,
  }));
  const links = [
    { source: "PE1PUX", target: "PD3V", id: 1 },
    { source: "LA7HKA", target: "pe1pux", id: 2 },
    { source: "LA7HKA", target: "OZ9JEP", id: 3 },
  ];

  it("keeps the selected station, its direct neighbours and incident links", () => {
    const graph = filterStationGraph(stations, links, "pe1pux");

    expect(graph.stations.map((station) => station.callsign)).toEqual(["PE1PUX", "PD3V", "LA7HKA"]);
    expect(graph.links.map((link) => link.id)).toEqual([1, 2]);
  });

  it("returns the complete graph when no filter is selected", () => {
    expect(filterStationGraph(stations, links, "")).toEqual({ stations, links });
  });

  it("keeps an unconnected selected station visible", () => {
    const graph = filterStationGraph(stations, links, "N0CALL");

    expect(graph.stations.map((station) => station.callsign)).toEqual(["N0CALL"]);
    expect(graph.links).toEqual([]);
  });
});

describe("grouped connection SNR", () => {
  it("averages only known finite SNR values", () => {
    expect(averageSnr([-12, -6, null, undefined])).toBe(-9);
    expect(averageSnr([3, Number.NaN, 6])).toBe(4.5);
  });

  it("returns no value when a grouped endpoint has no SNR observations", () => {
    expect(averageSnr([null, undefined, Number.NaN])).toBeNull();
  });
});

describe("stored timestamps", () => {
  it("interprets SQLite timestamps as UTC", () => {
    expect(parseStoredUtc("2026-08-07T12:00:00").toISOString()).toBe("2026-08-07T12:00:00.000Z");
  });

  it("preserves an explicit offset", () => {
    expect(parseStoredUtc("2026-08-07T14:00:00+02:00").toISOString()).toBe(
      "2026-08-07T12:00:00.000Z",
    );
  });
});

describe("error display", () => {
  it("keeps useful API error details", () => {
    expect(errorMessage({ detail: "connection failed" })).toBe('{"detail":"connection failed"}');
    expect(errorMessage(new Error("timeout"))).toBe("timeout");
    expect(errorMessage(undefined)).toBe("undefined");
  });
});
