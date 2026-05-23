import { expect, test } from "@playwright/test";
import { uniqueLocalUser } from "../../fixtures/test-env";

test.describe("Owner Session Persistence and Auth Integrity Sweep", () => {
  // Routine A: Worker Onboarding/Creation Persistence assertions
  test("TEST ROUTINE A: Worker Onboarding and Creation Persistence", async ({ page }) => {
    const owner = uniqueLocalUser();
    const ownerPhone = owner.phone;
    const ownerPassword = owner.password;

    // 1. Authenticate fully with standard Factory Owner credentials
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
      console.log("Unique Owner account does not exist. Registering...");
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

    // 2. Navigate to Onboarding segment form workspace
    await page.goto("/onboarding");
    await expect(page.getByRole("heading", { name: "Onboarding Wizard" })).toBeVisible();

    // 3. Input dummy entry records for worker and click save/submit (ensure 10 digits)
    const suffix = `${Date.now()}${Math.floor(Math.random() * 1000)}`.slice(-8);
    await page.getByLabel("Name").fill(`E2E Worker ${suffix}`);
    await page.getByRole("textbox", { name: "Mobile Number" }).fill(`91${suffix}`);
    await page.getByLabel("Daily wages").fill("600");
    await page.getByLabel("Duty hours").fill("8");

    // Click "Save Worker" to save
    await page.getByRole("button", { name: "Save Worker" }).click();

    // 4. Assert that we remain logged in and layout context is NOT corrupted
    await expect(page.getByText(/saved/i)).toBeVisible();
    await expect(page).not.toHaveURL(/.*\/login/);
    
    // Explicitly go to dashboard first to see the overview heading
    await page.goto("/dashboard");
    await expect(page.getByRole("heading", { name: "Live Factory Overview" })).toBeVisible();
  });

  // Routine B: Audit Scanner Matrix across Multi-Tenant Creation Terminals
  test("TEST ROUTINE B: Audit Scanner Matrix across Multi-Tenant Creation Terminals", async ({ page }) => {
    const owner = uniqueLocalUser();
    const ownerPhone = owner.phone;
    const ownerPassword = owner.password;

    // Login Owner
    await page.goto("/login");
    await page.getByLabel("Email or Mobile Number").fill(ownerPhone);
    await page.locator('[data-testid="staff-password-input"] input').fill(ownerPassword);
    await page.locator("form").filter({ has: page.getByLabel("Email or Mobile Number") }).getByRole("button", { name: "Login", exact: true }).click();

    let loggedIn = false;
    try {
      await expect(page).toHaveURL(/\/dashboard/, { timeout: 3000 });
      loggedIn = true;
    } catch {
      console.log("Unique Owner account does not exist. Registering...");
    }

    if (!loggedIn) {
      await page.getByRole("button", { name: "Sign Up" }).click();
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

    // Terminals to loop through
    const terminals = [
      {
        name: "Supervisor Creation",
        path: "/staff",
        setup: async () => {
          const suffix = `${Date.now()}${Math.floor(Math.random() * 1000)}`.slice(-8);
          await page.getByTestId("staff-full-name-input").fill(`Scanner Supervisor ${suffix}`);
          await page.getByRole("textbox", { name: "Mobile Number" }).fill(`87${suffix}`);
          await page.locator('[data-testid="staff-password-input"] input').fill("superPassword");
          await page.locator('[data-testid="staff-confirm-password-input"] input').fill("superPassword");
          await page.getByTestId("staff-role-select").selectOption("supervisor");
          await page.getByTestId("save-staff-button").click();
          await expect(page.getByText(/created successfully/i)).toBeVisible();
        }
      },
      {
        name: "Customer Entry Registry",
        path: "/customers",
        setup: async () => {
          const suffix = `${Date.now()}${Math.floor(Math.random() * 1000)}`.slice(-8);
          await page.getByLabel("Phone Number").fill(`92${suffix}`);
          await page.getByLabel("Customer Name").fill(`Scanner Customer ${suffix}`);
          await page.getByLabel("Company Name").fill(`Scanner Corp ${suffix}`);
          await page.getByLabel("Place / City").fill("Scanner City");
          await page.getByRole("button", { name: "Save Customer" }).click();
          await expect(page.getByText(/saved/i)).toBeVisible();
        }
      },
      {
        name: "Expense Onboarding Form",
        path: "/expenses",
        setup: async () => {
          const suffix = `${Date.now()}${Math.floor(Math.random() * 1000)}`.slice(-8);
          await page.getByLabel("Expense Name").fill(`Scanner Expense ${suffix}`);
          await page.getByLabel("Amount").fill("4500");
          await page.getByRole("button", { name: "Add Expense" }).click();
          await expect(page.getByText(/added/i)).toBeVisible();
        }
      }
    ];

    for (const term of terminals) {
      console.log(`Executing ${term.name} Sweep...`);
      await page.goto(term.path);
      await term.setup();

      // Assert that we are NOT logged out (assert token exists in localStorage and URL is not login)
      const token = await page.evaluate(() => localStorage.getItem("token") || localStorage.getItem("ai_erp_token"));
      expect(token).not.toBeNull();
      expect(token).not.toBe("");
      await expect(page).not.toHaveURL(/.*\/login/);
    }
  });
});
