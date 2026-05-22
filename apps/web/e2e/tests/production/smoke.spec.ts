import { testEnv } from "../../fixtures/test-env";
import { expect, test } from "../../fixtures/diagnostics";
import { DashboardPage } from "../../pages/DashboardPage";
import { LoginPage } from "../../pages/LoginPage";
import { RouteTester } from "../../pages/RouteTester";

test.use({ baseURL: process.env.PLAYWRIGHT_BASE_URL || "https://munshiai.co.in" });

const productionSmokeRoutes = [
  { path: "/dashboard", heading: "Live Factory Overview" },
  { path: "/profile", heading: "My Profile" },
  { path: "/inventory", heading: "Live Inventory" },
  { path: "/production", heading: "Production Entry" },
  { path: "/customers", heading: "Customers" },
  { path: "/expenses", heading: "Factory Expenses" },
];

test.describe("production smoke", () => {
  test("homepage and login page load without client/API failures", async ({ page, diagnostics }) => {
    await page.goto("/");
    await expect(page.locator("body")).toBeVisible();
    await expect(page.getByRole("link", { name: /login/i }).first()).toBeVisible();

    await page.goto("/login");
    await new LoginPage(page).expectVisible();
    diagnostics.expectClean();
  });

  test("existing test user can open dashboard and main protected routes", async ({ page, diagnostics }) => {
    const identifier = testEnv.phone || testEnv.email;
    test.skip(!identifier || !testEnv.password, "Set PLAYWRIGHT_TEST_EMAIL or PLAYWRIGHT_TEST_PHONE plus PLAYWRIGHT_TEST_PASSWORD to run authenticated production smoke.");

    const login = new LoginPage(page);
    await login.goto();
    await login.login(identifier, testEnv.password);
    await new DashboardPage(page).expectLoaded();
    await login.expectAuthStorage();

    const routeTester = new RouteTester(page);
    for (const route of productionSmokeRoutes) {
      await routeTester.expectProtectedRouteOpens(route);
    }
    diagnostics.expectClean();
  });
});
