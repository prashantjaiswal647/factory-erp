import { uniqueLocalUser } from "../../fixtures/test-env";
import { expect, test } from "../../fixtures/diagnostics";
import { DashboardPage } from "../../pages/DashboardPage";
import { LoginPage } from "../../pages/LoginPage";
import { ownerProtectedRoutes, RouteTester } from "../../pages/RouteTester";
import { SignupPage } from "../../pages/SignupPage";

test.describe("local protected ERP routes", () => {
  test.beforeEach(async ({ page }) => {
    const user = uniqueLocalUser();
    const signup = new SignupPage(page);
    const login = new LoginPage(page);
    const dashboard = new DashboardPage(page);

    await signup.goto();
    await signup.signup(user);
    await login.login(user.phone, user.password);
    await dashboard.expectLoaded();
  });

  for (const route of ownerProtectedRoutes) {
    test(`${route.path} opens after login`, async ({ page, diagnostics }) => {
      await new RouteTester(page).expectProtectedRouteOpens(route);
      diagnostics.expectClean();
    });
  }

  test("factory expenses validates required fields and submits valid data", async ({ page, diagnostics }) => {
    const expenseName = `E2E QA Expense ${Date.now()}`;

    await page.goto("/expenses");
    await expect(page.getByRole("heading", { name: "Factory Expenses" })).toBeVisible();

    await page.getByRole("button", { name: "Add Expense" }).click();
    await expect(page.getByText("Expense name and amount are required.")).toBeVisible();

    await page.getByLabel("Expense Name").fill(expenseName);
    await page.getByLabel("Amount").fill("125");
    await page.getByRole("button", { name: "Add Expense" }).click();

    await expect(page.getByText("Expense added")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("cell", { name: expenseName })).toBeVisible();
    diagnostics.expectClean();
  });

  test("profile edit validates invalid mobile number", async ({ page }) => {
    await page.goto("/profile");
    await expect(page.getByRole("heading", { name: "My Profile" })).toBeVisible();
    await page.getByRole("button", { name: "Edit Profile" }).click();
    await page.getByRole("textbox", { name: "Mobile Number" }).fill("123");
    await page.getByRole("button", { name: "Save Changes" }).click();
    await expect(page.getByText("Please enter a valid mobile number for the selected country.")).toBeVisible();
  });
});
