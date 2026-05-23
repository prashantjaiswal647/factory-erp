import { expect, test } from "@playwright/test";
import { uniqueLocalUser } from "../fixtures/test-env";

test.describe("System Resilience & Global Stability Integrity Suite", () => {
  test("Assert that deformed payloads and timeouts never trigger crashes or session drops", async ({ page }) => {
    const owner = uniqueLocalUser();
    const ownerPhone = owner.phone;
    const ownerPassword = owner.password;

    // 1. Setup Playwright Interceptions before hitting routes
    // Mock /api/billing/plans -> Return deformed object
    await page.route("**/api/billing/plans", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "deformed_object" }),
      });
    });

    // Mock /api/v1/staff/list -> Return null
    await page.route("**/api/v1/staff/list", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: "null",
      });
    });

    // Mock /api/production/daily -> Network timeout simulation
    await page.route("**/api/production/daily", async (route) => {
      await route.abort("timedout");
    });

    // 2. Perform Owner login flow with registration fallback
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "Secure Login" })).toBeVisible();

    await page.getByLabel("Email or Mobile Number").fill(ownerPhone);
    await page.locator('[data-testid="staff-password-input"] input').fill(ownerPassword);
    await page.locator("form").filter({ has: page.getByLabel("Email or Mobile Number") }).getByRole("button", { name: "Login", exact: true }).click();

    let loggedIn = false;
    try {
      await expect(page).toHaveURL(/\/dashboard/, { timeout: 3000 });
      loggedIn = true;
    } catch {
      console.log("Placeholder Owner account does not exist. Performing auto-registration...");
    }

    if (!loggedIn) {
      // Click on "Sign Up" tab
      await page.getByRole("button", { name: "Sign Up" }).click();
      await expect(page.getByRole("heading", { name: "Create Owner Account" })).toBeVisible();

      // Sign up placeholder Owner
      await page.getByLabel("Full Name").fill(owner.fullName);
      await page.getByLabel("Email").fill(owner.email);
      await page.getByRole("textbox", { name: "Mobile Number" }).fill(ownerPhone);
      await page.getByLabel("Factory Name").fill(owner.factoryName);
      await page.locator('[data-testid="signup-password-input"] input').fill(ownerPassword);
      await page.locator('[data-testid="signup-confirm-password-input"] input').fill(ownerPassword);
      await page.locator("form").filter({ has: page.getByLabel("Full Name") }).getByRole("button", { name: "Sign Up", exact: true }).click();

      // Wait for success notice and switch back to Login
      await expect(page.getByText(/successful/i)).toBeVisible();
      
      // Perform Login again
      await page.getByLabel("Email or Mobile Number").fill(ownerPhone);
      await page.locator('[data-testid="staff-password-input"] input').fill(ownerPassword);
      await page.locator("form").filter({ has: page.getByLabel("Email or Mobile Number") }).getByRole("button", { name: "Login", exact: true }).click();
      
      // Assert dashboard boots successfully
      await expect(page).toHaveURL(/\/dashboard/);
    }

    // 3. Test Staff page resilience (Expected: Safe render of staff grid with NO unhandled crashes or logout)
    await page.goto("/staff");
    await expect(page.getByRole("heading", { name: "Staff Management" })).toBeVisible();
    
    // Assert the page loaded gracefully and shows the empty state without crash
    await expect(page.getByText(/No staff accounts registered/i)).toBeVisible();
    await expect(page).toHaveURL(/\/staff/); // Ensure session is intact and no accidental logout to /login occurred

    // 4. Test Billing Plans section resilience (Expected: Graceful rendering using fallback plans)
    await page.goto("/billing");
    await expect(page.getByText("Plans & Pricing")).toBeVisible();
    
    // Verify that plans cards are rendered anyway using the client-side default/fallback list
    await expect(page.getByRole("heading", { name: "Basic Plan" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Growth Plan" })).toBeVisible();
    await expect(page).toHaveURL(/\/billing/); // Session intact

    // 5. Test Production Page network failure timeout resilience
    await page.goto("/production");
    await expect(page.getByRole("heading", { name: "Production Entry" })).toBeVisible();

    // Fill production entry form
    await page.getByLabel("Total Boxes Made").fill("15");
    await page.getByLabel("Loose Packets Made").fill("5");
    await page.getByLabel("Wastage Amount (KG)").fill("1");

    // Click "Save Production"
    await page.getByRole("button", { name: "Save Production" }).click();

    // Assert that the page displays the error gracefully and keeps user session active
    await expect(page.getByText(/failed/i).or(page.getByText(/timeout/i)).or(page.getByText(/network/i))).toBeVisible();
    await expect(page).toHaveURL(/\/production/); // Session remains active
  });
});
