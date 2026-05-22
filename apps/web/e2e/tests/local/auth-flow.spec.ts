import { apiHealthCandidates, uniqueLocalUser } from "../../fixtures/test-env";
import { expect, test } from "../../fixtures/diagnostics";
import { DashboardPage } from "../../pages/DashboardPage";
import { LoginPage } from "../../pages/LoginPage";
import { SignupPage } from "../../pages/SignupPage";

test.describe("local auth and subscription-safe startup", () => {
  test("app and API health endpoints are reachable", async ({ page, request, baseURL, diagnostics }) => {
    await page.goto("/");
    await expect(page.locator("body")).toBeVisible();
    await expect(page.getByRole("link", { name: /login/i }).first()).toBeVisible();

    const candidates = apiHealthCandidates(baseURL || "http://localhost:5173");
    const responses = await Promise.all(
      candidates.map(async (url) => {
        try {
          return { url, response: await request.get(url, { timeout: 5_000 }) };
        } catch {
          return { url, response: null };
        }
      }),
    );
    const healthy = responses.find(({ response }) => response?.ok());
    expect(healthy, `Expected one health endpoint to respond: ${candidates.join(", ")}`).toBeTruthy();
    diagnostics.expectClean();
  });

  test("signup validation, signup, phone-only login, auth storage, and dashboard load", async ({ page, diagnostics }) => {
    const user = uniqueLocalUser();
    const signup = new SignupPage(page);
    const login = new LoginPage(page);
    const dashboard = new DashboardPage(page);

    await signup.goto();
    await signup.expectVisible();
    await signup.expectIndiaDefault();

    await signup.submitEmpty();
    await expect(page.getByLabel("Full Name")).toBeFocused();

    await page.getByLabel("Full Name").fill(user.fullName);
    await page.getByLabel("Email").fill(user.email);
    await page.getByRole("textbox", { name: "Mobile Number" }).fill("123");
    await page.getByLabel("Factory Name").fill(user.factoryName);
    await page.getByLabel("Password", { exact: true }).fill(user.password);
    await page.getByLabel("Confirm Password", { exact: true }).fill(user.password);
    await page.locator("form").filter({ has: page.getByLabel("Full Name") }).getByRole("button", { name: "Sign Up", exact: true }).click();
    await expect(page.getByText(/valid mobile number/i)).toBeVisible();

    await page.getByRole("textbox", { name: "Mobile Number" }).fill("");
    await signup.signup(user);

    await login.expectVisible();
    await login.login(user.phone, user.password);
    await dashboard.expectLoaded();
    await login.expectAuthStorage();
    diagnostics.expectClean();
  });

  test("protected dashboard redirects unauthenticated users to login", async ({ page }) => {
    await page.goto("/dashboard");

    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByRole("heading", { name: "Secure Login" })).toBeVisible();
  });
});
