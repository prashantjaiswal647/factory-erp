import { expect, type Page } from "@playwright/test";

export class DashboardPage {
  constructor(private readonly page: Page) {}

  async expectLoaded() {
    await expect(this.page).toHaveURL(/\/dashboard$/);
    const heading = this.page.getByTestId("dashboard-heading");
    await expect(heading).toBeVisible({ timeout: 20_000 });
    await expect(heading).toContainText(/Welcome back|Live Factory Overview/);
  }

  async refreshData() {
    await this.page.getByRole("button", { name: /refresh data/i }).click();
  }
}
