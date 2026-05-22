import { expect, test } from "../../fixtures/diagnostics";
import { createAndLoginOwner } from "../../fixtures/auth";

test.describe("UX - navigation", () => {
  test("sidebar navigation highlights active route and browser history works", async ({ page, diagnostics }) => {
    await createAndLoginOwner(page);

    const dashboardLink = page.getByRole("link", { name: "Dashboard" });
    await expect(dashboardLink).toHaveClass(/bg-\[#F3E8FF\]/);

    await page.getByRole("link", { name: "Inventory" }).click();
    await expect(page).toHaveURL(/\/inventory$/);
    await expect(page.getByRole("heading", { name: "Live Inventory" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Inventory" })).toHaveClass(/bg-\[#F3E8FF\]/);

    await page.goBack();
    await expect(page).toHaveURL(/\/dashboard$/);
    await expect(page.getByRole("heading", { name: "Live Factory Overview" })).toBeVisible();

    await page.goForward();
    await expect(page).toHaveURL(/\/inventory$/);
    await expect(page.getByRole("heading", { name: "Live Inventory" })).toBeVisible();
    diagnostics.expectClean();
  });

  test("protected routes redirect unauthenticated users to login", async ({ page }) => {
    await page.goto("/production");
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByRole("heading", { name: "Secure Login" })).toBeVisible();
  });
});
