import { defineConfig, devices } from "@playwright/test";

const isProductionSuite = process.argv.some((arg) => arg.includes("e2e/tests/production"));
const baseURL = process.env.PLAYWRIGHT_BASE_URL || (isProductionSuite ? "https://munshiai.co.in" : "http://localhost:5173");
const isLocal = /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?/i.test(baseURL);
const localPort = (() => {
  try {
    return new URL(baseURL).port || "5173";
  } catch {
    return "5173";
  }
})();

export default defineConfig({
  testDir: "./e2e/tests",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 1,
  workers: process.env.CI ? 1 : undefined,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL,
    browserName: "chromium",
    screenshot: "only-on-failure",
    trace: "on-first-retry",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: isLocal
    ? {
        command: `npm run dev -- --port ${localPort}`,
        url: baseURL,
        reuseExistingServer: !process.env.CI && process.env.PLAYWRIGHT_REUSE_SERVER === "1",
        timeout: 120_000,
      }
    : undefined,
});
