import { expect, test } from "@playwright/test";
import { uniqueLocalUser } from "../../fixtures/test-env";

test.describe("Staff Management Flow and Identity Auditing", () => {
  // Step A: Launch browser context, log in with verified placeholder Factory Owner credentials
  test("Orchestrate entire staff lifecycle and zero leakage assertions", async ({ page, context }) => {
    const owner = uniqueLocalUser();
    const ownerPhone = owner.phone;
    const ownerPassword = owner.password;

    const suffix = `${Date.now()}${Math.floor(Math.random() * 1000)}`.slice(-8);
    const staffPhone = `85${suffix}`;
    const staffPassword = "staffSecurePassword";

    // 1. Visit Login page
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "Secure Login" })).toBeVisible();

    // Try logging in with the placeholder owner credentials
    await page.getByLabel("Email or Mobile Number").fill(ownerPhone);
    await page.locator('[data-testid="staff-password-input"] input').fill(ownerPassword);
    await page.locator("form").filter({ has: page.getByLabel("Email or Mobile Number") }).getByRole("button", { name: "Login", exact: true }).click();

    // Assert dashboard boots successfully (or register if the account does not exist yet)
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

    // Step B: Navigate to /staff and assert strictly NO factory_id leakage
    await page.goto("/staff");
    await expect(page.getByRole("heading", { name: "Staff Management" })).toBeVisible();
    
    // Strict multi-tenant Zero leakage assertions: No factory_id or similar numeric/text identifiers visibly rendered
    const bodyText = await page.locator("body").innerText();
    expect(bodyText).not.toMatch(/factory[_\s-]?id/i);
    expect(bodyText).not.toMatch(/factory id/i);
    
    // Also assert that no elements contain custom data attributes named factory_id
    const factoryIdAttributes = await page.locator("[data-factory-id]").count();
    expect(factoryIdAttributes).toBe(0);

    // Step C: Locate asset elements and programmatically input Supervisor details
    // If the Supervisor is already registered from a previous run, delete it first to ensure idempotency
    const existingStaffRow = page.locator("tr", { hasText: `+91${staffPhone}` });
    if (await existingStaffRow.isVisible().catch(() => false)) {
      console.log("Supervisor already exists. Deleting first to reset context...");
      await existingStaffRow.getByTestId("delete-staff-button").click();
      await page.getByRole("button", { name: "Revoke Access" }).click();
      await expect(page.getByText(/revoked/i)).toBeVisible();
    }

    // Now proceed with supervisor creation
    await page.getByTestId("staff-full-name-input").fill("Test Supervisor");
    await page.getByRole("textbox", { name: "Mobile Number" }).fill(staffPhone);
    
    // Test visibility toggle on password input
    const pwdInput = page.locator('[data-testid="staff-password-input"] input');
    const pwdToggle = page.locator('[data-testid="staff-password-input"] button');
    
    await pwdInput.fill(staffPassword);
    await expect(pwdInput).toHaveAttribute("type", "password");
    await pwdToggle.click();
    await expect(pwdInput).toHaveAttribute("type", "text");
    await pwdToggle.click();
    await expect(pwdInput).toHaveAttribute("type", "password");

    // Test visibility toggle on confirm password input
    const confirmPwdInput = page.locator('[data-testid="staff-confirm-password-input"] input');
    const confirmPwdToggle = page.locator('[data-testid="staff-confirm-password-input"] button');
    await confirmPwdInput.fill(staffPassword);
    await confirmPwdToggle.click();
    await expect(confirmPwdInput).toHaveAttribute("type", "text");
    await confirmPwdToggle.click();
    await expect(confirmPwdInput).toHaveAttribute("type", "password");

    // Select Supervisor role and save
    await page.getByTestId("staff-role-select").selectOption("supervisor");
    await page.getByTestId("save-staff-button").click();

    // Verify successful creation and listing
    await expect(page.getByText(/created successfully/i)).toBeVisible();
    await expect(page.locator("tr", { hasText: "Test Supervisor" })).toBeVisible();

    // Step D: Target data row, verify inline edit updates, and trigger Edit mutation
    const staffRow = page.locator("tr", { hasText: "Test Supervisor" });
    await staffRow.getByTestId("edit-staff-button").click();

    // Edit modal form fields check
    await expect(page.getByRole("heading", { name: "Edit Staff Account" })).toBeVisible();
    await page.locator('input[value="Test Supervisor"]').fill("Test Supervisor Updated");
    await page.getByRole("button", { name: "Save Changes" }).click();

    // Verify inline flush updates in view registry table
    await expect(page.getByText(/updated successfully/i)).toBeVisible();
    await expect(page.locator("tr", { hasText: "Test Supervisor Updated" })).toBeVisible();

    // Step E: Clear entire browser storage session context
    await context.clearCookies();
    await page.evaluate(() => localStorage.clear());
    await page.evaluate(() => sessionStorage.clear());

    // Step F: Reload login workspace and authenticate with newly created supervisor credentials
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "Secure Login" })).toBeVisible();

    // Sign in as supervisor
    await page.getByLabel("Email or Mobile Number").fill(staffPhone);
    
    // Verify password visibility toggle on login password
    const loginPwdInput = page.locator('[data-testid="staff-password-input"] input');
    const loginPwdToggle = page.locator('[data-testid="staff-password-input"] button');
    await loginPwdInput.fill(staffPassword);
    await expect(loginPwdInput).toHaveAttribute("type", "password");
    await loginPwdToggle.click();
    await expect(loginPwdInput).toHaveAttribute("type", "text");
    await loginPwdToggle.click();
    await expect(loginPwdInput).toHaveAttribute("type", "password");

    // Submit credentials
    await page.locator("form").filter({ has: page.getByLabel("Email or Mobile Number") }).getByRole("button", { name: "Login", exact: true }).click();

    // Explicitly assert successful login and direct redirection to the role-appropriate landing route
    await expect(page).toHaveURL(/\/production/);
    
    // Verify restricted view: supervisor should NOT see owner actions like "Staff Management" sidebar option
    await expect(page.getByRole("link", { name: /staff/i })).not.toBeVisible();
  });
});
