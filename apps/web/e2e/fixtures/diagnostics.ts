import { expect, test as base } from "@playwright/test";
import type { Page, TestInfo } from "@playwright/test";

type DiagnosticEntry = {
  type: "console" | "requestfailed" | "api";
  message: string;
};

export type Diagnostics = {
  entries: DiagnosticEntry[];
  clear: () => void;
  expectClean: () => void;
};

const ignoredConsoleFragments = [
  "Download the React DevTools",
  "Google login setup pending",
];

export const test = base.extend<{ diagnostics: Diagnostics }>({
  diagnostics: [
    async ({ page }, use, testInfo) => {
      const entries: DiagnosticEntry[] = [];
      attachDiagnostics(page, entries);

      await use({
        entries,
        clear: () => {
          entries.splice(0, entries.length);
        },
        expectClean: () => {
          expect(entries, formatDiagnostics(entries)).toEqual([]);
        },
      });

      if (entries.length > 0) {
        await testInfo.attach("client-diagnostics", {
          body: formatDiagnostics(entries),
          contentType: "text/plain",
        });
      }
    },
    { auto: true },
  ],
});

export { expect };

function attachDiagnostics(page: Page, entries: DiagnosticEntry[]) {
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    const text = message.text();
    if (ignoredConsoleFragments.some((fragment) => text.includes(fragment))) return;
    entries.push({ type: "console", message: text });
  });

  page.on("requestfailed", (request) => {
    const failure = request.failure();
    const url = request.url();
    if (failure?.errorText === "net::ERR_ABORTED" && !url.includes("localhost:8000") && !url.includes("/api/")) {
      return;
    }
    entries.push({
      type: "requestfailed",
      message: `${request.method()} ${url} ${failure?.errorText || "request failed"}`,
    });
  });

  page.on("response", (response) => {
    const status = response.status();
    const url = response.url();
    const isApi = /\/api\/|:8000\/|\/health$/.test(url);
    if (!isApi || status < 400) return;
    entries.push({ type: "api", message: `${status} ${response.request().method()} ${url}` });
  });
}

export function formatDiagnostics(entries: DiagnosticEntry[]) {
  if (entries.length === 0) return "No console errors, failed requests, or API 4xx/5xx responses captured.";
  return entries.map((entry) => `[${entry.type}] ${entry.message}`).join("\n");
}

export function attachBugContext(testInfo: TestInfo, body: string) {
  return testInfo.attach("bug-context", {
    body,
    contentType: "text/plain",
  });
}
