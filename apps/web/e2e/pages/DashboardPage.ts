import { expect, type Page } from "@playwright/test";

export class DashboardPage {
  constructor(private readonly page: Page) {}

  async expectLoaded() {
    await expect(this.page).toHaveURL(/\/dashboard$/);
    await expect(this.page.getByRole("heading", { name: "Live Factory Overview" })).toBeVisible({ timeout: 20_000 });
    await expect(this.page.getByText(/Factory Operations|Munshi AI/).first()).toBeVisible();
  }

  async refreshData() {
    await this.page.getByRole("button", { name: /refresh data/i }).click();
  }
}
