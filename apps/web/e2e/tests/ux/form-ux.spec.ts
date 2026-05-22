import { expect, test } from "../../fixtures/diagnostics";
import { createAndLoginOwner } from "../../fixtures/auth";
import { SignupPage } from "../../pages/SignupPage";

test.describe("UX - forms", () => {
  test("signup form shows required and invalid mobile validation", async ({ page, diagnostics }) => {
    const signup = new SignupPage(page);

    await signup.goto();
    await signup.expectVisible();
    await signup.expectIndiaDefault();

    await signup.submitEmpty();
    await expect(page.getByLabel("Full Name")).toBeFocused();

    await page.getByLabel("Full Name").fill("UX Test Owner");
    await page.getByLabel("Email").fill("ux.invalid@example.test");
    await page.getByRole("textbox", { name: "Mobile Number" }).fill("123");
    await page.getByLabel("Factory Name").fill("UX Test Factory");
    await page.getByLabel("Password", { exact: true }).fill("UxTest@12345");
    await page.getByLabel("Confirm Password", { exact: true }).fill("UxTest@12345");
    await page.locator("form").filter({ has: page.getByLabel("Full Name") }).getByRole("button", { name: "Sign Up", exact: true }).click();

    await expect(page.getByText(/valid mobile number/i)).toBeVisible();
    diagnostics.expectClean();
  });

  test("expense form handles validation, loading state, success toast, and duplicate-submit guard", async ({ page, diagnostics }) => {
    await createAndLoginOwner(page);
    await page.goto("/expenses");

    await page.getByRole("button", { name: "Add Expense" }).click();
    await expect(page.getByText("Expense name and amount are required.")).toBeVisible();

    let postCount = 0;
    await page.route("**/api/expenses", async (route) => {
      if (route.request().method() === "POST") {
        postCount += 1;
        await new Promise((resolve) => setTimeout(resolve, 700));
      }
      await route.continue();
    });

    const expenseName = `UX Expense ${Date.now()}`;
    await page.getByLabel("Expense Name").fill(expenseName);
    await page.getByLabel("Amount").fill("75");
    await page.getByRole("button", { name: "Add Expense" }).click();
    await expect(page.getByRole("button", { name: "Adding..." })).toBeDisabled();
    await page.getByRole("button", { name: "Adding..." }).click({ force: true });

    await expect(page.getByText("Expense added")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("cell", { name: expenseName })).toBeVisible();
    expect(postCount).toBe(1);
    diagnostics.expectClean();
  });

  test("expense form surfaces API errors without navigating away", async ({ page }) => {
    test.fail(true, "Known UX issue UX-001: failed expense submissions do not surface a visible error message.");
    await createAndLoginOwner(page);
    await page.goto("/expenses");
    await page.route("**/api/expenses", async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "Forced UX failure" }) });
        return;
      }
      await route.continue();
    });

    await page.getByLabel("Expense Name").fill("UX Failed Expense");
    await page.getByLabel("Amount").fill("85");
    await page.getByRole("button", { name: "Add Expense" }).click();

    await expect(page.getByText(/Forced UX failure|failed|error/i)).toBeVisible({ timeout: 5_000 });
    await expect(page.getByRole("heading", { name: "Factory Expenses" })).toBeVisible();
  });
});
