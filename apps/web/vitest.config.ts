import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setupTests.ts"],
    exclude: [
      "node_modules/**",
      "dist/**",
      "e2e/**",
      "**/*.spec.ts",
      "**/*.spec.tsx",
      "playwright.config.*",
    ],
  },
});
