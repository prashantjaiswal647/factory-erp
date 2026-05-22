import AxeBuilder from "@axe-core/playwright";

import { expect, test } from "../../fixtures/diagnostics";
import { createAndLoginOwner } from "../../fixtures/auth";

test.describe("UX - accessibility", () => {
  test("login page supports keyboard navigation and visible focus", async ({ page, diagnostics }) => {
    await page.goto("/login");

    await page.keyboard.press("Tab");
    await expect(page.locator(":focus")).toBeVisible();
    await page.keyboard.press("Tab");
    await expect(page.locator(":focus")).toBeVisible();
    await page.keyboard.press("Tab");
    await expect(page.locator(":focus")).toBeVisible();

    await expect(page.getByLabel("Email or Mobile Number").or(page.getByLabel("Phone Number"))).toBeVisible();
    await expect(page.getByLabel("Password")).toBeVisible();
    diagnostics.expectClean();
  });

  test("basic axe scan on login page has no serious or critical violations", async ({ page }) => {
    await page.goto("/login");

    const results = await new AxeBuilder({ page }).analyze();
    const severe = results.violations.filter((violation) => ["serious", "critical"].includes(violation.impact || ""));
    expect(severe, JSON.stringify(severe, null, 2)).toEqual([]);
  });

  test("basic axe scan on dashboard has no serious or critical violations", async ({ page }) => {
    await createAndLoginOwner(page);

    const results = await new AxeBuilder({ page }).analyze();
    const severe = results.violations.filter((violation) => ["serious", "critical"].includes(violation.impact || ""));
    expect(severe, JSON.stringify(severe, null, 2)).toEqual([]);
  });
});
