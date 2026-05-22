import { expect, test } from "../../fixtures/diagnostics";
import { createAndLoginOwner } from "../../fixtures/auth";

const mobileViewports = [
  { name: "iPhone 14", viewport: { width: 390, height: 844 } },
  { name: "Samsung Galaxy S23", viewport: { width: 360, height: 780 } },
  { name: "iPad", viewport: { width: 768, height: 1024 } },
];

for (const viewport of mobileViewports) {
  test.describe(`UX - mobile - ${viewport.name}`, () => {
    test("dashboard, sidebar, forms, and tables remain usable without page-level horizontal scroll", async ({ page, diagnostics }) => {
      await page.setViewportSize(viewport.viewport);
      await createAndLoginOwner(page);

      await expectNoHorizontalScroll(page);
      await page.getByRole("button", { name: "Open navigation" }).click();
      await expect(page.getByRole("link", { name: "Inventory" })).toBeVisible();
      await page.getByRole("link", { name: "Inventory" }).click();
      await expect(page.getByRole("heading", { name: "Live Inventory" })).toBeVisible();
      await expectNoHorizontalScroll(page);
      await expect(page.locator(".overflow-x-auto").first().or(page.getByText("No stock rows found."))).toBeVisible();

      await page.getByRole("button", { name: "Open navigation" }).click();
      await page.getByRole("link", { name: "Factory Expenses" }).click();
      await expect(page.getByRole("heading", { name: "Factory Expenses" })).toBeVisible();
      await expect(page.getByLabel("Expense Name")).toBeVisible();
      await expect(page.getByLabel("Amount")).toBeVisible();
      await expectNoHorizontalScroll(page);
      diagnostics.expectClean();
    });
  });
}

async function expectNoHorizontalScroll(page: import("@playwright/test").Page) {
  const scroll = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(scroll.scrollWidth, `Page has horizontal overflow: ${scroll.scrollWidth} > ${scroll.clientWidth}`).toBeLessThanOrEqual(scroll.clientWidth + 1);
}
