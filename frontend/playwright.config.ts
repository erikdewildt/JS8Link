import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  // Keep the local Vite test server stable on developer machines with limited
  // resources. The suite uses isolated page state, so parallel workers add
  // little value but can make the shared webServer disappear mid-run.
  workers: 1,
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:8018",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 8018",
    cwd: ".",
    url: "http://127.0.0.1:8018",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
