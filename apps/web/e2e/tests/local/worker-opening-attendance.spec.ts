import { expect, test } from "@playwright/test";
import { uniqueLocalUser } from "../../fixtures/test-env";

test.describe("Worker Opening Attendance and Settlement E2E Flow", () => {
  test("Integrates opening attendance during onboarding, daily ledger checks, and merged salary calculations", async ({ page, context }) => {
    const owner = uniqueLocalUser();
    const ownerPhone = owner.phone;
    const ownerPassword = owner.password;

    const suffix = `${Date.now()}${Math.floor(Math.random() * 1000)}`.slice(-8);
    const workerPhone = `87${suffix}`;
    const workerPassword = "workerSecurePassword123";
    const workerName = `Worker OA E2E ${suffix}`;

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
    // Step 2: Go to Staff Management and verify zero leakage
    // -------------------------------------------------------------
    await page.goto("/staff");
    await expect(page.getByRole("heading", { name: "Staff Management" })).toBeVisible();

    // Check no factory_id leaks on UI
    const bodyText = await page.locator("body").innerText();
    expect(bodyText).not.toMatch(/factory[_\s-]?id/i);
    expect(bodyText).not.toMatch(/tenant[_\s-]?id/i);

    // -------------------------------------------------------------
    // Step 3: Create worker with opening attendance
    // -------------------------------------------------------------
    await page.getByTestId("staff-full-name-input").fill(workerName);
    await page.getByRole("textbox", { name: "Mobile Number" }).fill(workerPhone);
    await page.locator('[data-testid="staff-password-input"] input').fill(workerPassword);
    await page.locator('[data-testid="staff-confirm-password-input"] input').fill(workerPassword);
    await page.getByTestId("staff-role-select").selectOption("worker");

    // Toggle opening attendance section
    await page.getByTestId("opening-attendance-toggle").check();
    await expect(page.getByTestId("opening-attendance-section")).toBeVisible();

    // Fill opening attendance values: May 1st to May 15th
    await page.getByTestId("opening-period-start").fill("2026-05-01");
    await page.getByTestId("opening-period-end").fill("2026-05-15");
    await page.getByTestId("opening-present-days").fill("12");
    await page.getByTestId("opening-half-days").fill("1");
    await page.getByTestId("opening-absent-days").fill("2");
    await page.locator('label').filter({ hasText: /^Paid Leave$/ }).locator('input').fill("0");
    await page.getByTestId("opening-overtime-hours").fill("4");
    await page.getByTestId("opening-advance-paid").fill("1000");
    await page.locator('label').filter({ hasText: /^Deductions$/ }).locator('input').fill("100");
    await page.getByPlaceholder("Add some notes...").fill("Onboarding historical record");

    // Save
    await page.getByTestId("save-staff-button").click();
    await expect(page.getByText(/created successfully/i)).toBeVisible();

    // -------------------------------------------------------------
    // Step 4: Verify opening attendance display & database persistence
    // -------------------------------------------------------------
    // Verify row summary exists
    const staffRow = page.locator("tr", { hasText: workerName });
    await expect(staffRow).toBeVisible();
    await expect(staffRow.getByTestId("staff-opening-attendance-summary")).toContainText("Prev Att: 12P / 1H (2026-05-01 to 2026-05-15)");

    // Refresh and assert DB persistence
    await page.reload();
    await expect(page.locator("tr", { hasText: workerName })).toBeVisible();
    await expect(page.locator("tr", { hasText: workerName }).getByTestId("staff-opening-attendance-summary")).toContainText("Prev Att: 12P / 1H (2026-05-01 to 2026-05-15)");

    // -------------------------------------------------------------
    // Step 5: Check daily ledger warning and overlap handling
    // -------------------------------------------------------------
    await page.goto("/attendance");
    await expect(page.getByRole("heading", { name: "Attendance & Worker Ledger" })).toBeVisible();

    // Find our worker's row and click "View Ledger"
    const attendanceRow = page.locator("tr", { hasText: workerName });
    await expect(attendanceRow).toBeVisible();
    await attendanceRow.getByRole("button", { name: "View Ledger" }).click();

    // Target ledger drawer container specifically using unique helper text
    const ledgerDrawer = page.locator("aside", { hasText: "date-wise duty" });
    await expect(ledgerDrawer).toBeVisible();

    // Look for a date inside the opening period: e.g. 2026-05-10
    // Check that it renders the "Opening Period" warning text
    const dateRow = ledgerDrawer.locator("tr", { hasText: "2026-05-10" });
    await expect(dateRow).toBeVisible();
    await expect(dateRow.getByText("Opening Period")).toBeVisible();

    // -------------------------------------------------------------
    // Step 6: Preview Settlement and check calculation integration
    // -------------------------------------------------------------
    // Click "Clear Hisab" to open the settlement modal
    await ledgerDrawer.getByRole("button", { name: "Clear Hisab" }).click();
    await expect(page.getByRole("heading", { name: "Clear Hisab" })).toBeVisible();

    // Preview
    await page.getByRole("button", { name: "Preview" }).click();

    // Verify calculation metrics precisely using exact XPath sibling selectors
    const totalDutyVal = page.locator('xpath=//p[text()="Total Duty"]/following-sibling::p');
    await expect(totalDutyVal).toContainText("Rs 0");

    const advanceDeductedVal = page.locator('xpath=//p[text()="Advance Deducted"]/following-sibling::p');
    await expect(advanceDeductedVal).toContainText("Rs 1,100");

    const netPayableVal = page.locator('xpath=//p[text()="Net Payable"]/following-sibling::p');
    await expect(netPayableVal).toContainText("Rs -1,100");

    // Close the Hisab modal
    await page.getByRole("button", { name: "x" }).click();

    // Close the Ledger drawer specifically
    await ledgerDrawer.locator("button").first().click();
    await expect(ledgerDrawer).not.toBeVisible();
  });
});
