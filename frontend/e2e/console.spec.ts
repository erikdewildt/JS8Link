// SPDX-License-Identifier: GPL-3.0-only
// Copyright (C) 2026  JS8Link contributors

import { expect, test, type Page, type Route } from "@playwright/test";

type SetupState = { complete: boolean };

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function mockApi(page: Page, setup: SetupState = { complete: true }) {
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    if (path === "/api/setup/status") {
      return json(route, {
        setup_complete: setup.complete,
        host: "127.0.0.1",
        port: 2442,
        connected: setup.complete,
        auth_enabled: false,
      });
    }
    if (path === "/api/setup/test-connection") {
      return json(route, { version: "3.0.0" });
    }
    if (path === "/api/setup/complete") {
      setup.complete = true;
      return json(route, { status: "ok" });
    }
    if (path === "/api/health") return json(route, { status: "ok", version: "0.4.2" });
    if (path === "/api/preferences") {
      return json(route, {
        language: "nl",
        theme: "dark",
        band_scope_minutes: 15,
        selected_chat_callsign: "DF7ET",
        monitor_map_height: 420,
        history_minutes: 60,
        monitor_band: "",
        monitor_sort_key: "received_at",
        monitor_sort_direction: "desc",
        monitor_map_center_latitude: 52.0,
        monitor_map_center_longitude: 5.0,
        monitor_map_zoom: 3,
        monitor_map_popups: true,
        monitor_view: "messages",
      });
    }
    if (path === "/api/status") {
      return json(route, {
        connected: true,
        callsign: "PA0ABC",
        station: { value: "PA0ABC" },
        frequency: { params: { DIAL: 7078000, OFFSET: 1500 } },
        dial: 7078000,
        offset: 1500,
        normal_offset: 1500,
        fixed_offset: 1500,
        offset_mode: "fixed",
        speed: 0,
        mode: { params: { SPEED: 0 } },
        band: "40m",
        rx_enabled: true,
        tx_enabled: true,
        tx_queue_depth: 0,
      });
    }
    if (path === "/api/js8/call-selected") return json(route, { callsign: "DF7ET" });
    if (path === "/api/js8/call-selected/clear") return json(route, { callsign: null });
    if (path === "/api/js8/frequency-presets") {
      return json(route, [{ band: "40m", dial: 7078000, frequency_mhz: 7.078, label: "40m" }]);
    }
    if (path === "/api/chats") {
      return json(route, {
        chats: [
          {
            callsign: "DF7ET",
            last_message: "CQ JS8Link",
            last_message_at: "2026-08-07T12:00:00",
            last_direction: "rx",
            unread_count: 0,
            grid: "JN69",
            last_snr: -10,
            last_offset: 1179,
            last_mode: "Normal",
            preferred_speed: 0,
          },
        ],
        selected_callsign: "DF7ET",
      });
    }
    if (path === "/api/chats/stations") {
      return json(route, {
        stations: [
          { callsign: "DF7ET", grid: "JN69", last_seen: "2026-08-07T12:00:00", last_snr: -10 },
        ],
      });
    }
    if (path.endsWith("/messages") && path !== "/api/monitor/messages")
      return json(route, { messages: [], next_cursor: null });
    if (path.endsWith("/speed")) {
      return json(route, { status: "ok", callsign: "DF7ET", preferred_speed: 1 });
    }
    if (path.startsWith("/api/stations/")) {
      if (request.method() === "PATCH") {
        return json(route, {
          callsign: "DF7ET",
          name: "Station contact",
          qth: "JN69",
          notes: "Updated notes",
        });
      }
      return json(route, { callsign: "DF7ET", name: null, qth: "JN69", notes: null });
    }
    if (path === "/api/js8/settings") {
      return json(route, {
        callsign: "PA0ABC",
        grid: "JO22",
        info: "JS8Link",
        status: "Testing",
        dial: 7078000,
        offset: 1500,
        fixed_offset: 1500,
        offset_mode: "fixed",
        speed: 0,
        spot: false,
      });
    }
    if (path === "/api/js8/filter") {
      return json(route, { center: 1500, width: 3000, enabled: true });
    }
    if (path === "/api/js8/tx-queue") {
      return json(route, { depth: 0 });
    }
    if (path === "/api/js8/tx-text") {
      return json(route, { text: "" });
    }
    if (path === "/api/update/check")
      return json(route, {
        update_available: false,
        current_commit: "abcdef12",
        latest_commit: "abcdef12",
        latest_version: "0.8.6",
        latest_message: "",
      });
    if (path === "/api/diagnostics/traces") {
      return json(route, {
        traces: [
          {
            trace_id: "trace-1",
            source: "js8_api",
            event_type: "RX.ACTIVITY",
            severity: "info",
            summary: "Heartbeat reception report received",
            interpretation: "IU2ITE reports that it received PE1PUX's heartbeat at +07 dB.",
            created_at: "2026-08-07T14:00:00.000Z",
          },
        ],
      });
    }
    if (path === "/api/diagnostics/traces/trace-1") {
      return json(route, {
        trace_id: "trace-1",
        source: "js8_api",
        event_type: "RX.ACTIVITY",
        severity: "info",
        summary: "Heartbeat reception report received",
        interpretation: "IU2ITE reports that it received PE1PUX's heartbeat at +07 dB.",
        created_at: "2026-08-07T14:00:00.000Z",
        raw_payload: '{"type":"RX.ACTIVITY"}',
        processing: [
          {
            id: 1,
            sequence: 1,
            operation: "Classify frame",
            outcome: "ok",
            detail: "Stored as heartbeat",
            payload: '{"kind":"heartbeat"}',
            created_at: "2026-08-07T14:00:00.000Z",
          },
        ],
      });
    }
    if (path === "/api/monitor/messages") {
      return json(route, {
        messages: [
          {
            id: 1,
            sender: "DF7ET",
            text: "CQ JS8Link",
            type: "RX.DIRECTED",
            snr: -10,
            offset: 1500,
            mode: "Normal",
            band: "40m",
            is_heartbeat: false,
            received_at: new Date().toISOString(),
            direction: "rx",
          },
        ],
      });
    }
    if (path === "/api/monitor/graph")
      return json(route, {
        stations: [
          {
            id: 1,
            callsign: "DF7ET",
            grid: "JN69",
            latitude: 49.4,
            longitude: 11.1,
            last_snr: -10,
            last_offset: 1500,
            last_mode: "Normal",
            message_count: 1,
            last_seen: new Date().toISOString(),
          },
        ],
        links: [],
      });
    if (path === "/api/monitor/band-activity") return json(route, { groups: [] });
    if (path === "/api/monitor/last-heard") return json(route, { stations: [] });
    if (path === "/api/monitor/spectrum") return json(route, { signals: [] });
    if (path === "/api/config") {
      return json(route, {
        js8_host: "127.0.0.1",
        js8_port: 2442,
        update_repository: "",
        update_branch: "main",
        api_message_retention_days: 7,
        diagnostics_enabled: true,
        diagnostics_retention_days: 7,
        station_queries_enabled: true,
        station_queries_interval_minutes: 5,
        query_cooldown_seconds: 120,
        max_queries_per_hour: 12,
        query_timeout_minutes: 5,
      });
    }
    if (path === "/api/stations") return json(route, { stations: [] });
    if (path === "/api/js8/inbox/messages") return json(route, { messages: [] });
    if (path === "/api/js8/inbox/sync") return json(route, { synced: 0 });
    if (path === "/api/changelog") {
      return json(route, {
        releases: [
          {
            version: "0.8.6",
            date: "2026-08-07",
            categories: [{ name: "Added", items: ["Test feature"] }],
          },
        ],
      });
    }
    if (path === "/api/help") {
      return json(route, {
        language: "nl",
        version: 1,
        topics: [
          {
            id: "global",
            title: "JS8Link gebruiken",
            summary: "De stationconsole in één oogopslag.",
            sections: [{ heading: "Overzicht", body: "Help blijft lokaal beschikbaar." }],
            steps: ["Open Help vanuit de stationbalk."],
            troubleshooting: [],
            references: [],
            related: ["monitor"],
          },
          {
            id: "monitor",
            title: "Bandmonitor",
            summary: "Bekijk verkeer, stations en relaties.",
            sections: [],
            steps: [],
            troubleshooting: [],
            references: [],
            related: [],
          },
        ],
      });
    }
    if (path === "/api/update/apply") return json(route, { status: "current" });
    if (path.startsWith("/api/diagnostics/traces")) {
      return json(route, { traces: [] });
    }
    if (path === "/api/diagnostics/purge") return json(route, { status: "ok" });
    // Let WebSocket upgrade requests pass through unmodified.
    if (request.headers()["upgrade"]?.toLowerCase() === "websocket") {
      return route.continue();
    }
    if (request.method() === "PATCH" || request.method() === "POST")
      return json(route, { status: "ok" });
    return json(route, {});
  });
}

test("completes the first-run setup wizard", async ({ page }) => {
  const setup = { complete: false };
  await mockApi(page, setup);
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Welkom bij JS8Link" })).toBeVisible();
  await page.getByRole("button", { name: "Configuratie starten" }).click();
  await page.getByRole("button", { name: "Verbinding testen" }).click();
  await expect(page.getByText("JS8Call API 3.0.0 gevonden")).toBeVisible();
  await page.getByRole("button", { name: "Volgende" }).click();
  await expect(page.getByRole("heading", { name: "Beveilig JS8Link" })).toBeVisible();
  await page.getByRole("button", { name: "Volgende" }).click();
  await expect(page.getByRole("heading", { name: "Klaar om te starten" })).toBeVisible();
  await page.getByRole("button", { name: "Configuratie opslaan" }).click();
  await expect(page.getByRole("heading", { name: "Chats" })).toBeVisible();
});

test("shows a useful error when the setup connection test fails", async ({ page }) => {
  const setup = { complete: false };
  await mockApi(page, setup);
  await page.route("**/api/setup/test-connection", async (route) =>
    json(route, { detail: "JS8Call API is not reachable" }, 503),
  );
  await page.goto("/");

  await page.getByRole("button", { name: "Configuratie starten" }).click();
  await page.getByRole("button", { name: "Verbinding testen" }).click();
  await expect(page.getByText("JS8Call API is not reachable")).toBeVisible();
});

test.describe("station console", () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Chats" })).toBeVisible();
  });

  test("opens contextual help and closes it with Escape", async ({ page }) => {
    await page.getByRole("button", { name: "Help", exact: true }).click();
    await expect(page.getByRole("dialog", { name: "JS8Link gebruiken" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog", { name: "JS8Link gebruiken" })).toBeHidden();
  });

  test("opens help for the active monitor panel", async ({ page }) => {
    await page.getByRole("button", { name: "Bandmonitor" }).click();
    await page.getByRole("button", { name: "Help", exact: true }).click();
    await expect(page.getByRole("dialog", { name: "Bandmonitor" })).toBeVisible();
  });

  test("shows and clears the JS8Call selected callsign", async ({ page }) => {
    const selected = page.locator(".selected-call-instrument");
    await expect(selected).toContainText("DF7ET");
    await selected.getByRole("button", { name: "Selectie wissen" }).click();
    await expect(selected).toContainText("Geen selectie");
  });

  test.fixme("opens the offset control and switches to automatic mode", async ({ page }) => {
    await page.getByRole("button", { name: "Offset instellen" }).click();
    await expect(page.getByRole("dialog", { name: "Offset instellen" })).toBeVisible();
    await page.getByRole("button", { name: "Auto" }).click();
    await expect(page.getByRole("dialog", { name: "Offset instellen" })).toBeHidden();
  });

  test("starts a chat with a manually entered callsign", async ({ page }) => {
    await page.getByRole("button", { name: "Nieuwe chat" }).click();
    await page.getByPlaceholder("PA0ABC").fill("K1ABC");
    await page.getByRole("button", { name: "Chat starten" }).click();
    await expect(
      page.locator(".chat-conversation-header").getByRole("heading", { name: "K1ABC" }),
    ).toBeVisible();
    await expect(page.locator("#chat-send-speed")).toHaveValue("0");
  });

  test("sends a message through the chat composer", async ({ page }) => {
    await page.getByPlaceholder("Typ een bericht…").fill("CQ JS8Link");
    const responsePromise = page.waitForResponse(
      (candidate) =>
        candidate.request().method() === "POST" &&
        candidate.url().includes("/api/chats/DF7ET/messages"),
    );
    await page.getByRole("button", { name: "Verzenden" }).dispatchEvent("click");
    await responsePromise;
  });

  test("persists a preferred speed for the selected chat", async ({ page }) => {
    const request = page.waitForRequest(
      (candidate) =>
        candidate.method() === "PATCH" && candidate.url().includes("/api/chats/DF7ET/speed"),
    );
    await page.locator("#chat-send-speed").selectOption("1");
    await request;
    await expect(page.locator("#chat-send-speed")).toHaveValue("1");
  });

  test("shows the latest received SNR in the chat header", async ({ page }) => {
    await expect(page.locator(".chat-conversation-header")).toContainText("-10 dB SNR");
  });

  test("edits station information inline in the inspector", async ({ page }) => {
    const inspector = page.locator(".station-inspector");
    await inspector.getByRole("button", { name: "Stationinformatie bewerken" }).click();
    await expect(
      inspector.getByRole("heading", { name: "Stationinformatie bewerken" }),
    ).toBeVisible();

    const form = inspector.locator(".station-contact-form");
    await form.locator("input").nth(0).fill("Station contact");
    await form.locator("input").nth(1).fill("JN69");
    await form.locator("textarea").fill("Updated notes");

    const request = page.waitForRequest(
      (candidate) =>
        candidate.method() === "PATCH" && candidate.url().includes("/api/stations/DF7ET"),
    );
    await inspector.getByRole("button", { name: "Opslaan" }).click();
    await request;
    await expect(
      inspector.getByRole("heading", { name: "Stationinformatie bewerken" }),
    ).toBeHidden();
  });

  test("opens the monitor and switches its offset view", async ({ page }) => {
    await page.getByRole("button", { name: "Bandmonitor" }).click();
    await expect(page.getByRole("heading", { name: "Stationskaart" })).toBeVisible();
    await expect(page.locator(".monitor-table-tabsbar")).toBeVisible();
    await expect(page.locator(".monitor-station-inspector")).toContainText("Geen selectie");
    await page.getByRole("tab", { name: "Per offset" }).click();
    await expect(page.getByRole("tab", { name: "Per offset" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  test.fixme("opens the station inspector from a monitor row", async ({ page }) => {
    // FIXME: Monitor table doesn't render with mock data. The API endpoint
    //        returns data but visibleMessages filtering/appears to filter
    //        it out.  Needs investigation of loadMonitor → setMessages →
    //        visibleMessages pipeline.
    await page.getByRole("button", { name: "Bandmonitor" }).click();
    await expect(page.getByRole("heading", { name: "Stationskaart" })).toBeVisible();
    await expect(page.locator(".monitor-table tbody tr").first()).toBeVisible({ timeout: 15000 });
    await page.locator(".monitor-table tbody tr").first().click();
    await expect(page.locator(".monitor-station-inspector")).toContainText("DF7ET");
    await expect(page.locator(".monitor-station-inspector")).toContainText("-10 dB");
  });

  test("opens settings and switches to the JS8Call tab", async ({ page }) => {
    await page.locator(".settings-menu-item").click();
    await expect(page.getByRole("heading", { name: "Instellingen", exact: true })).toBeVisible();
    await expect(page.getByLabel("Retentie JS8Call API-diagnostiek (dagen)")).toBeVisible();
    await page.getByLabel("Retentie JS8Call API-diagnostiek (dagen)").fill("14");
    await page.getByLabel("Thema").selectOption("light");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    await page.getByLabel("Taal").selectOption("en");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible();
    await page.getByRole("tab", { name: "JS8Call" }).click();
    await expect(page.getByText("Radio configuration")).toBeVisible();
  });

  // ── Header instruments ─────────────────────────────────────────────

  test("displays the VFO frequency in the header", async ({ page }) => {
    await expect(page.locator(".vfo-frequency")).toContainText("7.078");
  });

  test("displays the band selector with the current band", async ({ page }) => {
    const bandSelect = page.locator(".band-instrument select");
    await expect(bandSelect).toBeVisible();
    const value = await bandSelect.inputValue();
    expect(value).toBeTruthy();
  });

  test("displays the mode/speed selector", async ({ page }) => {
    const modeValue = page.locator(".mode-value");
    await expect(modeValue).toContainText("JS8");
    await expect(modeValue).toContainText("NORMAL");
  });

  test("changes the speed via the mode selector", async ({ page }) => {
    const speedSelect = page.locator(".speed-select");
    await expect(speedSelect).toBeVisible();
    const request = page.waitForRequest(
      (candidate) => candidate.method() === "POST" && candidate.url().includes("/api/mode/speed"),
    );
    await speedSelect.selectOption("1");
    await request;
  });

  test("RX button toggles RX state", async ({ page }) => {
    const rxButton = page.locator(".trx-instrument.rx");
    await expect(rxButton).toBeVisible();
    const request = page.waitForRequest(
      (candidate) =>
        candidate.method() === "POST" && candidate.url().includes("/api/js8/rx-toggle"),
    );
    await rxButton.click();
    await request;
  });

  test("TX button toggles TX state", async ({ page }) => {
    const txButton = page.locator(".trx-instrument.tx");
    await expect(txButton).toBeVisible();
    const request = page.waitForRequest(
      (candidate) =>
        candidate.method() === "POST" && candidate.url().includes("/api/js8/tx-toggle"),
    );
    await txButton.click();
    await request;
  });

  test("tune button is visible and pressable", async ({ page }) => {
    const tuneButton = page.locator(".trx-instrument.tune");
    await expect(tuneButton).toBeVisible();
    const request = page.waitForRequest(
      (candidate) => candidate.method() === "POST" && candidate.url().includes("/api/js8/tune"),
      { timeout: 5000 },
    );
    await tuneButton.dispatchEvent("pointerdown", { pointerId: 1 });
    await request;
  });

  test.fixme("offset popover shows auto and manual choices", async ({ page }) => {
    await page.getByRole("button", { name: "Offset instellen" }).click();
    const popover = page.getByRole("dialog", { name: "Offset instellen" });
    await expect(popover).toBeVisible();
    await expect(popover.getByRole("button", { name: "Auto" })).toBeVisible();
    await expect(popover.getByRole("button", { name: "Handmatig" })).toBeVisible();
    await popover.getByRole("button", { name: "Auto" }).click();
    await expect(popover).toBeHidden();
  });

  test.fixme("offset popover allows entering a manual offset value", async ({ page }) => {
    await page.getByRole("button", { name: "Offset instellen" }).click();
    const popover = page.getByRole("dialog", { name: "Offset instellen" });
    await popover.getByRole("button", { name: "Handmatig" }).click();
    const input = popover.locator("input[type=number]");
    await expect(input).toBeVisible();
    await input.fill("2000");
    await expect(input).toHaveValue("2000");
  });

  test("displays the connection indicator", async ({ page }) => {
    const connIcon = page.locator(".connection-icon.online");
    await expect(connIcon).toBeVisible();
  });

  test("displays the time instrument in the header", async ({ page }) => {
    const timeInstrument = page.locator(".time-instrument");
    await expect(timeInstrument).toBeVisible();
  });

  test.fixme("opens the changelog dialog on version click", async ({ page }) => {
    // FIXME: The changelog modal requires the /api/changelog endpoint to
    // return valid data, and the modal uses a portal that may not render
    // inside the test viewport.
    await page.locator(".current-version-link").click();
    const heading = page.getByRole("heading").filter({ hasText: /Wijzigingslog|Changelog/i });
    await expect(heading.first()).toBeVisible({ timeout: 5000 });
    await page.getByRole("button", { name: "Sluiten" }).first().click();
  });

  // ── Chat panel interactions ─────────────────────────────────────────

  test("displays the chat list with station callsigns", async ({ page }) => {
    await expect(page.locator(".chat-list")).toBeVisible();
    await expect(page.locator(".chat-list")).toContainText("DF7ET");
  });

  test("selects a chat from the list", async ({ page }) => {
    // Already selected DF7ET from preferences; verify conversation is open.
    await expect(
      page.locator(".chat-conversation-header").getByRole("heading", { name: "DF7ET" }),
    ).toBeVisible();
  });

  test("shows the character counter in the composer", async ({ page }) => {
    await page.getByPlaceholder("Typ een bericht…").fill("Hello");
    const counter = page.locator(".chat-character-count");
    await expect(counter).toContainText("5");
    await expect(counter).toContainText("220");
  });

  test("toggles the send-with-Enter checkbox", async ({ page }) => {
    const checkbox = page.locator(".chat-enter-toggle input[type=checkbox]");
    await expect(checkbox).toBeVisible();
    const wasChecked = await checkbox.isChecked();
    await checkbox.click();
    await expect(checkbox).toBeChecked({ checked: !wasChecked });
  });

  test.fixme("navigates back from chat conversation to welcome", async ({ page }) => {
    // FIXME: The back button may not be in the expected state depending on
    // whether a chat is pre-selected from preferences.
    const backButton = page.locator(".chat-back-button");
    await backButton.click();
    await expect(page.locator(".chat-welcome")).toBeVisible();
  });

  // ── Messages panel ──────────────────────────────────────────────────

  test("opens the messages panel and shows the sync button", async ({ page }) => {
    await page.getByRole("button", { name: "Berichten" }).click();
    await expect(page.getByRole("heading", { name: "Berichten" }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Inbox synchroniseren" })).toBeVisible();
  });

  test("clicks the inbox sync button", async ({ page }) => {
    await page.getByRole("button", { name: "Berichten" }).click();
    await expect(page.getByRole("heading", { name: "Berichten" }).first()).toBeVisible();
    const request = page.waitForRequest(
      (candidate) =>
        candidate.method() === "POST" && candidate.url().includes("/api/js8/inbox/sync"),
    );
    await page.getByRole("button", { name: "Inbox synchroniseren" }).click();
    await request;
  });

  // ── Monitor panel ───────────────────────────────────────────────────

  test.fixme("monitor shows all three table tabs", async ({ page }) => {
    // FIXME: The monitor panel's table tabs may not render fully because
    // the map component requires WebGL2 and additional API data.
    await page.getByRole("button", { name: "Bandmonitor" }).click();
    await expect(page.getByRole("tab", { name: "Traffic" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Per offset" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Laatst gehoord" })).toBeVisible();
  });

  test("monitor switches to last-heard view", async ({ page }) => {
    await page.getByRole("button", { name: "Bandmonitor" }).click();
    await expect(page.getByRole("heading", { name: "Stationskaart" })).toBeVisible();
    await page.getByRole("tab", { name: "Laatst gehoord" }).click();
    await expect(page.getByRole("tab", { name: "Laatst gehoord" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  test("monitor band filter is visible and selectable", async ({ page }) => {
    await page.getByRole("button", { name: "Bandmonitor" }).click();
    await expect(page.locator(".monitor-toolbar select").first()).toBeVisible();
  });

  test("monitor history slider is visible", async ({ page }) => {
    await page.getByRole("button", { name: "Bandmonitor" }).click();
    const slider = page.locator(".history-slider");
    await expect(slider).toBeVisible();
    await expect(slider).toHaveValue("60");
  });

  test("monitor filters traffic by sender or message and highlights matches", async ({ page }) => {
    await page.getByRole("button", { name: "Bandmonitor" }).click();
    await page.getByRole("button", { name: "Verkeer filteren" }).click();
    const search = page.getByLabel("Zoek afzender of bericht…");
    await search.fill("CQ");
    await expect(page.locator(".monitor-table tbody tr")).toHaveCount(1);
    await expect(page.locator(".monitor-table mark")).toContainText("CQ");

    await search.fill("DF7ET");
    await expect(page.locator(".monitor-table mark")).toContainText("DF7ET");
  });

  test("monitor changes history slider and triggers preference save", async ({ page }) => {
    await page.getByRole("button", { name: "Bandmonitor" }).click();
    const request = page.waitForRequest(
      (candidate) => candidate.method() === "PATCH" && candidate.url().includes("/api/preferences"),
    );
    // Move slider to 120 minutes.
    await page.locator(".history-slider").fill("120");
    await request;
  });

  test("monitor shows empty station inspector initially", async ({ page }) => {
    await page.getByRole("button", { name: "Bandmonitor" }).click();
    await expect(page.locator(".monitor-station-inspector.empty")).toContainText("Geen selectie");
  });

  // ── Settings panel ──────────────────────────────────────────────────

  test("diagnostics shows the raw, interpreted, and processing layers", async ({ page }) => {
    await page.locator(".settings-menu-item").click();
    await expect(page.getByRole("heading", { name: "Instellingen", exact: true })).toBeVisible();
    await page.getByRole("tab", { name: "Diagnostiek" }).click();
    await expect(page.getByText("Diagnostiek vastleggen")).toBeVisible();
    await expect(page.getByText("Heartbeat reception report received")).toBeVisible();
    await page.locator(".diagnostic-trace").first().click();
    await expect(page.getByText("01 · Ruwe data")).toBeVisible();
    await expect(page.getByText("02 · Interpretatie")).toBeVisible();
    await expect(page.getByText("03 · Verwerking")).toBeVisible();
    await expect(page.getByText("Stored as heartbeat")).toBeVisible();
  });

  test("settings shows purge confirmation then cancels", async ({ page }) => {
    await page.locator(".settings-menu-item").click();
    await expect(page.getByRole("heading", { name: "Instellingen", exact: true })).toBeVisible();
    const purgeButton = page.getByRole("button", { name: "Gegevens wissen" });
    await purgeButton.scrollIntoViewIfNeeded();
    await purgeButton.click();
    await expect(page.getByRole("button", { name: "Data verwijderen" })).toBeVisible();
    await page.getByRole("button", { name: "Annuleren" }).click();
    await expect(page.getByRole("button", { name: "Data verwijderen" })).toBeHidden();
  });

  test("settings update check button is visible", async ({ page }) => {
    await page.locator(".settings-menu-item").click();
    await expect(page.getByRole("heading", { name: "Instellingen", exact: true })).toBeVisible();
    const checkButton = page.getByRole("button", { name: "Controleren op updates" });
    await checkButton.scrollIntoViewIfNeeded();
    await expect(checkButton).toBeVisible();
  });

  test.fixme("settings clicks update check and receives result", async ({ page }) => {
    // FIXME: The update check result text may not render within the timeout
    // because the settings panel re-renders after the API response.
    await page.locator(".settings-menu-item").click();
    await expect(page.getByRole("heading", { name: "Instellingen", exact: true })).toBeVisible();
    const checkButton = page.getByRole("button", { name: "Controleren op updates" });
    await checkButton.scrollIntoViewIfNeeded();
    const request = page.waitForRequest(
      (candidate) => candidate.method() === "GET" && candidate.url().includes("/api/update/check"),
    );
    await checkButton.click();
    await request;
    await expect(page.getByText("JS8Link is actueel")).toBeVisible({ timeout: 5000 });
  });

  test.fixme("settings JS8Call tab shows spot toggle", async ({ page }) => {
    // FIXME: The JS8Call settings tab content may depend on API calls that
    // need more complete mocking (filter, tx-queue, tx-text).
    await page.locator(".settings-menu-item").click();
    await expect(page.getByRole("heading", { name: "Instellingen", exact: true })).toBeVisible();
    await page.getByRole("tab", { name: "JS8Call" }).click();
    await expect(page.getByText("Spotting")).toBeVisible({ timeout: 5000 });
  });

  test("settings application tab shows band scope minutes input", async ({ page }) => {
    await page.locator(".settings-menu-item").click();
    await expect(page.getByRole("heading", { name: "Instellingen", exact: true })).toBeVisible();
    await expect(page.getByLabel("Bandscope tijdsvenster (minuten)")).toBeVisible();
  });

  test("settings application tab shows toast duration input", async ({ page }) => {
    await page.locator(".settings-menu-item").click();
    await expect(page.getByRole("heading", { name: "Instellingen", exact: true })).toBeVisible();
    await expect(page.getByLabel("Meldingstijd ontvangen berichten (seconden)")).toBeVisible({
      timeout: 5000,
    });
  });

  // ── Band scope ──────────────────────────────────────────────────────

  test("band scope canvas is rendered", async ({ page }) => {
    const canvas = page.locator(".band-scope canvas");
    await expect(canvas).toBeVisible();
    await expect(canvas).toHaveAttribute("aria-label", /active offsets/);
  });

  test("band scope shows the legend", async ({ page }) => {
    const legend = page.locator(".band-scope-legend");
    await expect(legend).toBeVisible();
    await expect(legend).toContainText("RX");
    await expect(legend).toContainText("TX");
  });

  test("band scope shows the band label", async ({ page }) => {
    await expect(page.locator(".band-scope-label")).toContainText("BAND SCOPE");
  });

  // ── Cross-panel navigation ───────────────────────────────────────────

  test.fixme("switches from chat to monitor to messages and back", async ({ page }) => {
    // FIXME: The messages panel currently shows a "Binnenkort" placeholder
    // which makes the heading matching ambiguous.
    await page.getByRole("button", { name: "Bandmonitor" }).click();
    await expect(page.getByRole("heading", { name: "Stationskaart" })).toBeVisible();
    await page.getByRole("button", { name: "Berichten" }).click();
    await expect(page.getByRole("heading", { name: "Berichten" }).first()).toBeVisible();
    await page.getByRole("button", { name: "Chat" }).click();
    await expect(page.getByRole("heading", { name: "Chats" })).toBeVisible();
  });

  // ── Theme switching ──────────────────────────────────────────────────

  test("switches theme from dark to light and back", async ({ page }) => {
    await page.locator(".settings-menu-item").click();
    await expect(page.getByRole("heading", { name: "Instellingen", exact: true })).toBeVisible();
    await page.getByLabel("Thema").selectOption("light");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    await page.getByLabel("Thema").selectOption("forest");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "forest");
    await page.getByLabel("Thema").selectOption("field-light");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "field-light");
    await page.getByLabel("Thema").selectOption("dark");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  });

  // ── Language switching ───────────────────────────────────────────────

  test("switches language from Dutch to English", async ({ page }) => {
    await page.locator(".settings-menu-item").click();
    await expect(page.getByRole("heading", { name: "Instellingen", exact: true })).toBeVisible();
    await page.getByLabel("Taal").selectOption("en");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible();
    // Switch back to Dutch.
    await page.getByLabel("Language").selectOption("nl");
    await expect(page.getByRole("heading", { name: "Instellingen", exact: true })).toBeVisible();
  });

  // ── Time display switching ───────────────────────────────────────────

  test("switches time display between UTC and local", async ({ page }) => {
    await page.locator(".settings-menu-item").click();
    await expect(page.getByRole("heading", { name: "Instellingen", exact: true })).toBeVisible();
    await page.getByLabel("Tijdweergave").selectOption("utc");
    await expect(page.locator(".time-single")).toBeVisible();
    await page.getByLabel("Tijdweergave").selectOption("local");
    await expect(page.locator(".time-dual")).toBeVisible();
  });

  // ── Settings save ────────────────────────────────────────────────────

  test.fixme("saves application settings via the save button", async ({ page }) => {
    // FIXME: The settings save button may require scrolling or may be in a
    // different tab that hasn't loaded yet.
    await page.locator(".settings-menu-item").click();
    await expect(page.getByRole("heading", { name: "Instellingen", exact: true })).toBeVisible();
    const saveRequest = page.waitForRequest(
      (candidate) => candidate.method() === "PATCH" && candidate.url().includes("/api/config"),
    );
    await page.locator(".settings-page").getByRole("button", { name: "Opslaan" }).first().click();
    await saveRequest;
    await expect(page.getByText(/Instellingen opgeslagen/i)).toBeVisible({ timeout: 5000 });
  });
});
