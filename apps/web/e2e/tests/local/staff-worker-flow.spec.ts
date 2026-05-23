import { expect, test } from "@playwright/test";
import { uniqueLocalUser } from "../../fixtures/test-env";

test.describe("Worker (Operator) Management and Auth Flow", () => {
  test("Orchestrate entire worker lifecycle, database persistence, login checks, and zero leakage assertions", async ({ page, context }) => {
    const owner = uniqueLocalUser();
    const ownerPhone = owner.phone;
    const ownerPassword = owner.password;

    const suffix = `${Date.now()}${Math.floor(Math.random() * 1000)}`.slice(-8);
    const workerPhone = `86${suffix}`;
    const workerPassword = "workerSecurePassword123";

    // -------------------------------------------------------------
    // Step 1: Owner Login and Dashboard Setup
    // -------------------------------------------------------------
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
      console.log("Owner account does not exist. Performing auto-registration...");
    }

    if (!loggedIn) {
      await page.getByRole("button", { name: "Sign Up" }).click();
      await expect(page.getByRole("heading", { name: "Create Owner Account" })).toBeVisible();

      await page.getByLabel("Full Name").fill(owner.fullName);
      await page.getByLabel("Email").fill(owner.email);
      await page.getByRole("textbox", { name: "Mobile Number" }).fill(ownerPhone);
      await page.getByLabel("Factory Name").fill(owner.factoryName);
      await page.locator('[data-testid="signup-password-input"] input').fill(ownerPassword);
      await page.locator('[data-testid="signup-confirm-password-input"] input').fill(ownerPassword);
      await page.locator("form").filter({ has: page.getByLabel("Full Name") }).getByRole("button", { name: "Sign Up", exact: true }).click();

      await expect(page.getByText(/successful/i)).toBeVisible();

      await page.getByLabel("Email or Mobile Number").fill(ownerPhone);
      await page.locator('[data-testid="staff-password-input"] input').fill(ownerPassword);
      await page.locator("form").filter({ has: page.getByLabel("Email or Mobile Number") }).getByRole("button", { name: "Login", exact: true }).click();

      await expect(page).toHaveURL(/\/dashboard/);
    }

    // -------------------------------------------------------------
    // Test E: Zero factory_id / tenant_id UI Leakage Check
    // -------------------------------------------------------------
    await page.goto("/staff");
    await expect(page.getByRole("heading", { name: "Staff Management" })).toBeVisible();

    const bodyText = await page.locator("body").innerText();
    expect(bodyText).not.toMatch(/factory[_\s-]?id/i);
    expect(bodyText).not.toMatch(/tenant[_\s-]?id/i);
    expect(await page.locator("[data-factory-id]").count()).toBe(0);

    // -------------------------------------------------------------
    // Step 2: Clean up worker if they exist from a past run
    // -------------------------------------------------------------
    const existingStaffRow = page.locator("tr", { hasText: `+91${workerPhone}` });
    if (await existingStaffRow.isVisible().catch(() => false)) {
      console.log("Worker already exists. Deleting first to reset...");
      await existingStaffRow.getByTestId("delete-staff-button").click();
      await page.getByTestId("confirm-delete-staff-button").click();
      await expect(page.getByText(/revoked/i)).toBeVisible();
    }

    // -------------------------------------------------------------
    // Test F: Password & Confirm Password Visibility Toggles
    // -------------------------------------------------------------
    await page.getByTestId("staff-full-name-input").fill("Test Worker Operator");
    await page.getByRole("textbox", { name: "Mobile Number" }).fill(workerPhone);

    const pwdInput = page.locator('[data-testid="staff-password-input"] input');
    const pwdToggle = page.locator('[data-testid="staff-password-input"] button');
    await pwdInput.fill(workerPassword);
    await expect(pwdInput).toHaveAttribute("type", "password");
    await pwdToggle.click();
    await expect(pwdInput).toHaveAttribute("type", "text");
    await pwdToggle.click();
    await expect(pwdInput).toHaveAttribute("type", "password");

    const confirmPwdInput = page.locator('[data-testid="staff-confirm-password-input"] input');
    const confirmPwdToggle = page.locator('[data-testid="staff-confirm-password-input"] button');
    await confirmPwdInput.fill(workerPassword);
    await confirmPwdToggle.click();
    await expect(confirmPwdInput).toHaveAttribute("type", "text");
    await confirmPwdToggle.click();
    await expect(confirmPwdInput).toHaveAttribute("type", "password");

    // -------------------------------------------------------------
    // Test A: Owner creates worker and worker is saved (PostgreSQL)
    // -------------------------------------------------------------
    await page.getByTestId("staff-role-select").selectOption("worker");
    await page.getByTestId("save-staff-button").click();

    await expect(page.getByText(/created successfully/i)).toBeVisible();
    await expect(page.locator("tr", { hasText: "Test Worker Operator" })).toBeVisible();

    // Refresh page and assert persistence in database
    await page.reload();
    await expect(page.locator("tr", { hasText: "Test Worker Operator" })).toBeVisible();

    // -------------------------------------------------------------
    // Test B: Worker Login and Restricted Landing Redirection
    // -------------------------------------------------------------
    await context.clearCookies();
    await page.evaluate(() => localStorage.clear());
    await page.evaluate(() => sessionStorage.clear());

    await page.goto("/login");
    await page.getByLabel("Email or Mobile Number").fill(workerPhone);

    // Login page password visibility toggle check
    const loginPwdInput = page.locator('[data-testid="staff-password-input"] input');
    const loginPwdToggle = page.locator('[data-testid="staff-password-input"] button');
    await loginPwdInput.fill(workerPassword);
    await expect(loginPwdInput).toHaveAttribute("type", "password");
    await loginPwdToggle.click();
    await expect(loginPwdInput).toHaveAttribute("type", "text");
    await loginPwdToggle.click();
    await expect(loginPwdInput).toHaveAttribute("type", "password");

    await page.locator("form").filter({ has: page.getByLabel("Email or Mobile Number") }).getByRole("button", { name: "Login", exact: true }).click();

    // Redirected to role-appropriate inventory page
    await expect(page).toHaveURL(/\/inventory/);

    // Restricted UI Check: Worker must not see "Staff Management" in navigation
    await expect(page.getByRole("link", { name: /staff/i })).not.toBeVisible();

    // -------------------------------------------------------------
    // Test C: Owner Edits Worker Name and Status
    // -------------------------------------------------------------
    await context.clearCookies();
    await page.evaluate(() => localStorage.clear());
    await page.evaluate(() => sessionStorage.clear());

    await page.goto("/login");
    await page.getByLabel("Email or Mobile Number").fill(ownerPhone);
    await page.locator('[data-testid="staff-password-input"] input').fill(ownerPassword);
    await page.locator("form").filter({ has: page.getByLabel("Email or Mobile Number") }).getByRole("button", { name: "Login", exact: true }).click();
    await expect(page).toHaveURL(/\/dashboard/);

    await page.goto("/staff");
    const staffRow = page.locator("tr", { hasText: "Test Worker Operator" });
    await staffRow.getByTestId("edit-staff-button").click();

    await expect(page.getByRole("heading", { name: "Edit Staff Account" })).toBeVisible();
    await page.locator('input[value="Test Worker Operator"]').fill("Test Worker Operator Updated");
    await page.getByRole("button", { name: "Save Changes" }).click();

    await expect(page.getByText(/updated successfully/i)).toBeVisible();
    await expect(page.locator("tr", { hasText: "Test Worker Operator Updated" })).toBeVisible();

    // Refresh and verify persistence in database
    await page.reload();
    await expect(page.locator("tr", { hasText: "Test Worker Operator Updated" })).toBeVisible();

    // -------------------------------------------------------------
    // Test D: Owner Deletes/Deactivates Worker
    // -------------------------------------------------------------
    const updatedStaffRow = page.locator("tr", { hasText: "Test Worker Operator Updated" });
    await updatedStaffRow.getByTestId("delete-staff-button").click();
    await page.getByTestId("confirm-delete-staff-button").click();

    await expect(page.getByText(/revoked/i)).toBeVisible();
    await expect(page.locator("tr", { hasText: "Test Worker Operator Updated" })).not.toBeVisible();

    // Refresh and verify worker stays deleted in database
    await page.reload();
    await expect(page.locator("tr", { hasText: "Test Worker Operator Updated" })).not.toBeVisible();

    // Try logging in with the deleted credentials and assert it is blocked
    await context.clearCookies();
    await page.evaluate(() => localStorage.clear());
    await page.evaluate(() => sessionStorage.clear());

    await page.goto("/login");
    await page.getByLabel("Email or Mobile Number").fill(workerPhone);
    await page.locator('[data-testid="staff-password-input"] input').fill(workerPassword);
    await page.locator("form").filter({ has: page.getByLabel("Email or Mobile Number") }).getByRole("button", { name: "Login", exact: true }).click();

    // Ensure login is blocked (URL stays on /login, or displays unauthorized details)
    await expect(page.getByText(/incorrect/i).or(page.getByText(/denied/i)).or(page.getByText(/not found/i))).toBeVisible();
    expect(page.url()).toContain("/login");
  });
});
