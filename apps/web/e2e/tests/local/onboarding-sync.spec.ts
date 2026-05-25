import { expect, test } from "@playwright/test";
import { uniqueLocalUser } from "../../fixtures/test-env";

test.describe("Onboarding Wizard Material and Stock Sync E2E Test", () => {
  test("Should verify that saved onboarding raw materials, final stock, and packaging materials cleanly sync to dashboard and inventory page", async ({ page }) => {
    const owner = uniqueLocalUser();
    const ownerPhone = owner.phone;
    const ownerPassword = owner.password;

    // -------------------------------------------------------------
    // Step 1: Login / Sign Up the E2E Owner
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
      console.log("E2E Owner account does not exist. Performing registration...");
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

      // Sign up success can also lead to direct login or toast check
      await expect(page.locator("body")).toContainText(/successful/i);

      // Login now
      await page.getByLabel("Email or Mobile Number").fill(ownerPhone);
      await page.locator('[data-testid="staff-password-input"] input').fill(ownerPassword);
      await page.locator("form").filter({ has: page.getByLabel("Email or Mobile Number") }).getByRole("button", { name: "Login", exact: true }).click();

      await expect(page).toHaveURL(/\/dashboard/);
    }

    // -------------------------------------------------------------
    // Step 2: Go to Onboarding and fill Step 0 (Workers)
    // -------------------------------------------------------------
    await page.goto("/onboarding");
    await expect(page.getByRole("heading", { name: "Onboarding Wizard" })).toBeVisible();

    // Fill Worker
    const suffix = `${Date.now()}${Math.floor(Math.random() * 1000)}`.slice(-8);
    const workerName = `Worker Sync ${suffix}`;
    await page.getByLabel("Name").fill(workerName);
    await page.getByRole("textbox", { name: "Mobile Number" }).fill(`87${suffix}`);
    await page.getByLabel("Daily wages").fill("500");
    await page.getByLabel("Duty hours").fill("8");
    await page.getByRole("button", { name: "Save Worker" }).click();
    await expect(page.getByText(`${workerName} saved`)).toBeVisible();

    // Click "Machines" tab to go to Step 1
    await page.getByRole("button", { name: "Machines", exact: true }).click();
    await page.getByLabel("Machine no.").fill(`M-SYNC-${suffix.slice(-4)}`);
    await page.getByRole("button", { name: "Save Machines" }).click();
    await expect(page.getByText(/machines saved/i)).toBeVisible();

    // -------------------------------------------------------------
    // Step 3: Go to Raw Materials tab and fill Stocks
    // -------------------------------------------------------------
    await page.getByRole("button", { name: "Raw Materials", exact: true }).click();

    // 3.1 Save Blank Stock (210ml, 20kg per sack, 5 sacks = 100kg)
    await page.getByLabel("Size (ml)", { exact: true }).fill("210");
    await page.getByLabel("KG per Sack").fill("20");
    await page.getByLabel("Total Sacks").fill("5");
    await page.getByRole("button", { name: "Add Blank Stock" }).click();
    await expect(page.getByText(/blank stock saved/i)).toBeVisible();

    // 3.2 Save Bottom Stock (68mm, bag weight 15kg, rolls per bag 2, total bags 2)
    await page.getByLabel("Bottom Size (mm)").fill("68");
    await page.getByLabel("Bag Weight (kg)").fill("15");
    await page.getByLabel("Individual Rolls per Bag").fill("2");
    await page.getByLabel("Total Number of Bags").fill("2");
    await page.getByRole("button", { name: "Add Bottom Stock" }).click();
    await expect(page.getByText(/bottom stock saved/i)).toBeVisible();

    // 3.3 Save Box Stock (Big Box, quantity 100, price 15)
    await page.getByLabel("Box Type").selectOption("Big Box");
    await page.getByLabel("Box Quantity (Pieces)").fill("100");
    await page.getByLabel("Price per Box (Rs)").fill("15");
    await page.getByRole("button", { name: "Add Box Stock" }).click();
    await expect(page.getByText(/box stock saved/i)).toBeVisible();

    // 3.4 Save PP Plastic Stock ("Premium PP", cup size 210, 3 boras, 10kg each = 30kg)
    await page.getByLabel("Plastic Size/Type").fill("Premium PP");
    await page.getByLabel("Used for Cup Size (ml)").selectOption("210");
    await page.getByLabel("Total Boras (Sacks)").fill("3");
    await page.getByLabel("Weight per Bora (KG)").fill("10");
    await page.getByLabel("Price per KG (Rs)").fill("120");
    await page.getByRole("button", { name: "Add Plastic Stock" }).click();
    await expect(page.getByText(/plastic stock saved/i)).toBeVisible();

    // -------------------------------------------------------------
    // Step 4: Go to Final Product Stock tab and save stock
    // -------------------------------------------------------------
    await page.getByRole("button", { name: "Final Product Stock", exact: true }).click();
    await page.getByRole("button", { name: "Create Custom Entry", exact: true }).click();

    // Check custom size manual checkbox and type size 210
    await page.locator("input[type='checkbox']").check();
    await page.getByPlaceholder("Type custom size (e.g. 120)").fill("210");

    await page.getByLabel("Variety / Design").fill("Standard/White");
    await page.getByLabel("Packaging Size Name (Optional)").fill("210ml Standard Box");
    await page.getByLabel("Pcs / Packet").fill("100");
    await page.getByLabel("Packets / Box").fill("10");
    await page.getByLabel("Initial Quantity (Boxes)").fill("50");

    // Click Save Custom Opening Stock
    await page.getByRole("button", { name: "Save Custom Opening Stock" }).click();
    await expect(page.getByText(/final product opening stock saved/i)).toBeVisible();

    // -------------------------------------------------------------
    // Step 5: Go to Inventory page and verify all items display
    // -------------------------------------------------------------
    await page.goto("/inventory");
    await expect(page.getByRole("heading", { name: "Live Inventory" })).toBeVisible();

    // Check Blanks (100.0 kg)
    const blankRow = page.locator("tr", { hasText: "210ml Blank" });
    await expect(blankRow).toBeVisible();
    await expect(blankRow.locator("td").nth(2)).toContainText("100");

    // Check Bottoms (30.0 kg)
    const bottomRow = page.locator("tr", { hasText: "68mm Bottom Roll" });
    await expect(bottomRow).toBeVisible();
    await expect(bottomRow.locator("td").nth(2)).toContainText("30");

    // Check Carton Box (100 pieces)
    const boxRow = page.locator("tr", { hasText: "Big Box Carton Box" });
    await expect(boxRow).toBeVisible();
    await expect(boxRow.locator("td").nth(2)).toContainText("100");

    // Check Plastic/Polybag (30.0 kg)
    const plasticRow = page.locator("tr", { hasText: "Premium PP" });
    await expect(plasticRow).toBeVisible();
    await expect(plasticRow.locator("td").nth(2)).toContainText("30");

    // Check Final Product boxes (50)
    const finalRow = page.locator("tr", { hasText: "210ml Standard/White - 210ml Standard Box" });
    await expect(finalRow).toBeVisible();
    await expect(finalRow.locator("td").nth(2)).toContainText("50");

    // -------------------------------------------------------------
    // Step 6: Go to Dashboard and verify metrics visual charts
    // -------------------------------------------------------------
    await page.goto("/dashboard");
    await expect(page.getByRole("heading", { name: "Live Factory Overview" })).toBeVisible();

    // Check Bottom Stock Summary block displays 68mm size roll with weight 30.0 and 4 rolls
    const dashboardBottomRow = page.locator("tr", { hasText: "68" });
    await expect(dashboardBottomRow).toBeVisible();
    await expect(dashboardBottomRow.locator("td").nth(1)).toContainText("30");
    await expect(dashboardBottomRow.locator("td").nth(2)).toContainText("4");

    // Check Material Analytics mapped cards display size 210ml Blank as mapped/complete
    await expect(page.getByText("210ml Blank")).toBeVisible();
    await expect(page.getByText("68mm Bottom")).toBeVisible();

    // Verify Recharts bar chart contains SKU Standard/White 210ml
    await expect(page.locator("body")).toContainText("210ml Standard");
  });
});
