import { expect, test } from "../../fixtures/diagnostics";

const adminEmail = process.env.PLAYWRIGHT_SUPER_ADMIN_EMAIL;
const adminPassword = process.env.PLAYWRIGHT_SUPER_ADMIN_PASSWORD;

test.use({ baseURL: process.env.PLAYWRIGHT_BASE_URL || "https://munshiai.co.in" });

test.describe("production super admin smoke", () => {
  test("admin login page loads and protected route blocks anonymous access", async ({ page }) => {
    await page.goto("/munshi-control-room");
    await expect(page.getByRole("heading", { name: "Super Admin Only" })).toBeVisible();

    await page.goto("/munshi-control-room/dashboard");
    await expect(page).toHaveURL(/\/munshi-control-room$/);
    await expect(page.getByRole("heading", { name: "Super Admin Only" })).toBeVisible();
  });

  test("super admin authenticated smoke when credentials are provided", async ({ page }) => {
    test.skip(!adminEmail || !adminPassword, "Set PLAYWRIGHT_SUPER_ADMIN_EMAIL and PLAYWRIGHT_SUPER_ADMIN_PASSWORD to run authenticated production super admin smoke.");

    await page.goto("/munshi-control-room");
    await page.getByLabel("Email").fill(adminEmail);
    await page.getByLabel("Password").fill(adminPassword);
    await page.getByRole("button", { name: "Enter Control Room" }).click();

    await expect(page).toHaveURL(/\/munshi-control-room\/dashboard$/);
    await expect(page.getByText("Platform Dashboard")).toBeVisible();
  });
});
