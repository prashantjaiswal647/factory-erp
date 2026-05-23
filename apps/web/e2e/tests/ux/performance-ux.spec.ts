import { expect, test } from "../../fixtures/diagnostics";
import { createAndLoginOwner } from "../../fixtures/auth";

test.describe("UX - performance and states", () => {
  test("landing page first content renders quickly", async ({ page, diagnostics }) => {
    const started = Date.now();
    await page.goto("/");
    await expect(page.getByRole("link", { name: /login/i }).first()).toBeVisible();
    const elapsed = Date.now() - started;

    expect(elapsed, `Landing first visible content took ${elapsed}ms`).toBeLessThan(5_000);
  });

  test("dashboard shows loading state and renders within an acceptable limit", async ({ page, diagnostics }) => {
    await createAndLoginOwner(page);
    await page.goto("/dashboard");
    const started = Date.now();
    diagnostics.clear();

    await page.reload();
    await expect(page.getByText("Loading live factory overview...")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Live Factory Overview" })).toBeVisible({ timeout: 20_000 });

    const elapsed = Date.now() - started;
    expect(elapsed, `Dashboard render took ${elapsed}ms`).toBeLessThan(20_000);
  });

  test("empty state is visible on a fresh factory expense table", async ({ page, diagnostics }) => {
    await createAndLoginOwner(page);
    await page.goto("/expenses");
    diagnostics.clear();

    await expect(page.getByText("No expenses added yet.")).toBeVisible();
    diagnostics.expectClean();
  });
});
