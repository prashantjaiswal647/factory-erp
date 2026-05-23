import { expect, test } from "../../fixtures/diagnostics";
import { createAndLoginOwner } from "../../fixtures/auth";

const adminEmail = process.env.PLAYWRIGHT_SUPER_ADMIN_EMAIL;
const adminPassword = process.env.PLAYWRIGHT_SUPER_ADMIN_PASSWORD;
const enableAdminMutationTests = process.env.PLAYWRIGHT_ENABLE_ADMIN_MUTATION_TESTS === "true";

test.describe("hidden super admin control room", () => {
  test("hidden admin route is not visible in normal navigation", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("munshi-control-room")).toHaveCount(0);

    await createAndLoginOwner(page);
    await expect(page.getByRole("link", { name: /control room|super admin/i })).toHaveCount(0);
    await expect(page.getByText("munshi-control-room")).toHaveCount(0);
  });

  test("unauthenticated protected admin route redirects to admin login", async ({ page }) => {
    await page.goto("/munshi-control-room/dashboard");
    await expect(page).toHaveURL(/\/munshi-control-room$/);
    await expect(page.getByRole("heading", { name: "Super Admin Only" })).toBeVisible();
  });

  test("normal factory owner session cannot access super admin dashboard", async ({ page }) => {
    await createAndLoginOwner(page);
    await page.goto("/munshi-control-room/dashboard");
    await expect(page).toHaveURL(/\/munshi-control-room$/);
    await expect(page.getByRole("heading", { name: "Super Admin Only" })).toBeVisible();
  });

  test("super admin can login and open protected pages", async ({ page }) => {
    test.skip(!adminEmail || !adminPassword, "Set PLAYWRIGHT_SUPER_ADMIN_EMAIL and PLAYWRIGHT_SUPER_ADMIN_PASSWORD to run authenticated super admin checks.");

    await page.goto("/munshi-control-room");
    await page.getByLabel("Email").fill(adminEmail);
    await page.getByLabel("Password", { exact: true }).fill(adminPassword);
    await page.getByRole("button", { name: "Enter Control Room" }).click();

    await expect(page).toHaveURL(/\/munshi-control-room\/dashboard$/);
    await expect(page.getByRole("heading", { name: "Munshi Control Room" })).toBeVisible();
    await expect(page.getByText("Platform Dashboard")).toBeVisible();

    await page.getByRole("link", { name: "Owners" }).click();
    await expect(page.getByText("Factory Owner Management")).toBeVisible();

    await page.getByRole("link", { name: "Factories" }).click();
    await expect(page.getByText("Factory Management")).toBeVisible();

    await page.getByRole("link", { name: "Subscriptions" }).click();
    await expect(page.getByText("Manual Subscription Management")).toBeVisible();

    await page.getByRole("link", { name: "Audit Logs" }).click();
    await expect(page.getByText("Audit Logs")).toBeVisible();
  });

  test("owners and factories empty states do not use mock data", async ({ page }) => {
    await page.addInitScript(() => sessionStorage.setItem("munshi_super_admin_token", "test-token"));
    await page.route("**/api/super-admin/owners**", async (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
    await page.route("**/api/super-admin/factories**", async (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));

    await page.goto("/munshi-control-room/owners");
    await expect(page.getByText("No real factory owners found yet.")).toBeVisible();
    await expect(page.getByText(/mock|demo|sample|dummy/i)).toHaveCount(0);

    await page.goto("/munshi-control-room/factories");
    await expect(page.getByText("No factories found.")).toBeVisible();
    await expect(page.getByText(/mock|demo|sample|dummy/i)).toHaveCount(0);
  });

  test("create factory owner form validates password confirmation", async ({ page }) => {
    await page.addInitScript(() => sessionStorage.setItem("munshi_super_admin_token", "test-token"));
    await page.route("**/api/super-admin/owners**", async (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));

    await page.goto("/munshi-control-room/owners");
    await page.getByRole("button", { name: "Add Factory Owner" }).click();
    await page.getByLabel("Owner Name").fill("QA Owner");
    await page.getByLabel("Phone Number").fill("9876543210");
    await page.getByLabel("Password", { exact: true }).fill("Password123");
    await page.getByLabel("Confirm Password").fill("Password456");
    await page.getByLabel("Factory Name").fill("QA Factory");
    await page.getByRole("button", { name: "Create Owner" }).click();
    await expect(page.getByText("Password and confirm password must match.")).toBeVisible();
  });

  test("factories bulk delete preview requires exact confirmation phrase", async ({ page }) => {
    await page.addInitScript(() => sessionStorage.setItem("munshi_super_admin_token", "test-token"));
    await page.route("**/api/super-admin/settings", async (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ bulk_delete_enabled: true, bulk_delete_max: 50 }) }));
    await page.route("**/api/super-admin/factories", async (route) => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        { id: 101, name: "Playwright Cleanup Factory", factory_name: "Playwright Cleanup Factory", owner: { full_name: "QA Owner", email: "qa@example.com", phone_number: "+919876543210" }, subscription_status: "trial_active", payment_status: "free", created_at: new Date().toISOString() },
      ]),
    }));
    await page.route("**/api/super-admin/factories/bulk-delete-preview", async (route) => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        factories: [{ factory_id: 101, factory_name: "Playwright Cleanup Factory", owner_name: "QA Owner", owner_email: "qa@example.com", owner_phone: "+919876543210", record_counts: { production: 0, inventory: 0, sales: 0, expenses: 0, payments: 0, staff: 1, attendance: 0, customers: 0, machines: 0, products: 0, subscriptions: 0, app_usage_logs: 0, token_usage_logs: 0, audit_logs: 0 } }],
        total_counts: { factories: 1, production: 0, inventory: 0, sales: 0, expenses: 0, payments: 0, staff: 1, attendance: 0, customers: 0, machines: 0, products: 0, subscriptions: 0, app_usage_logs: 0, token_usage_logs: 0, audit_logs: 0 },
      }),
    }));

    await page.goto("/munshi-control-room/factories");
    await page.getByTestId("factory-row-checkbox").first().check();
    await expect(page.getByText("1 factory selected")).toBeVisible();
    await page.getByTestId("bulk-delete-factories-button").click();
    await expect(page.getByTestId("bulk-delete-preview-modal")).toBeVisible();
    await expect(page.getByTestId("bulk-delete-final-button")).toBeDisabled();
    await page.getByTestId("bulk-delete-confirmation-input").fill("DELETE FACTORIES");
    await expect(page.getByTestId("bulk-delete-final-button")).toBeDisabled();
    await page.getByTestId("bulk-delete-confirmation-input").fill("DELETE SELECTED FACTORIES");
    await expect(page.getByTestId("bulk-delete-final-button")).toBeEnabled();
  });

  test("bulk delete final action is blocked when server disables it", async ({ page }) => {
    await page.addInitScript(() => sessionStorage.setItem("munshi_super_admin_token", "test-token"));
    await page.route("**/api/super-admin/settings", async (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ bulk_delete_enabled: false, bulk_delete_max: 50 }) }));
    await page.route("**/api/super-admin/factories", async (route) => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([{ id: 102, name: "Delete Disabled Factory", factory_name: "Delete Disabled Factory", owner: null, subscription_status: "trial_active", payment_status: "free", created_at: new Date().toISOString() }]),
    }));
    await page.route("**/api/super-admin/factories/bulk-delete-preview", async (route) => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        factories: [{ factory_id: 102, factory_name: "Delete Disabled Factory", owner_name: null, owner_email: null, owner_phone: null, record_counts: { production: 0, inventory: 0, sales: 0, expenses: 0, payments: 0, staff: 0, attendance: 0, customers: 0, machines: 0, products: 0, subscriptions: 0, app_usage_logs: 0, token_usage_logs: 0, audit_logs: 0 } }],
        total_counts: { factories: 1, production: 0, inventory: 0, sales: 0, expenses: 0, payments: 0, staff: 0, attendance: 0, customers: 0, machines: 0, products: 0, subscriptions: 0, app_usage_logs: 0, token_usage_logs: 0, audit_logs: 0 },
      }),
    }));

    await page.goto("/munshi-control-room/factories");
    await expect(page.getByText("Bulk delete is disabled by server configuration.")).toBeVisible();
    await page.getByTestId("factory-row-checkbox").first().check();
    await page.getByTestId("bulk-delete-factories-button").click();
    await page.getByTestId("bulk-delete-confirmation-input").fill("DELETE SELECTED FACTORIES");
    await expect(page.getByTestId("bulk-delete-final-button")).toBeDisabled();
  });

  test("manual owner creation mutation is opt-in", async ({ page }) => {
    test.skip(!enableAdminMutationTests || !adminEmail || !adminPassword, "Set super admin credentials and PLAYWRIGHT_ENABLE_ADMIN_MUTATION_TESTS=true to run admin mutation checks.");

    await page.goto("/munshi-control-room");
    await page.getByLabel("Email").fill(adminEmail);
    await page.getByLabel("Password", { exact: true }).fill(adminPassword);
    await page.getByRole("button", { name: "Enter Control Room" }).click();
    await page.getByRole("link", { name: "Owners" }).click();
    await page.getByRole("button", { name: "Add Factory Owner" }).click();
    await expect(page.getByRole("heading", { name: "Add Factory Owner" })).toBeVisible();
  });
});
