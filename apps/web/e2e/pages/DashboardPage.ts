import { expect, type Page } from "@playwright/test";

export class DashboardPage {
  constructor(private readonly page: Page) {}

  async expectLoaded() {
    await expect(this.page).toHaveURL(/\/dashboard$/);
    await expect(this.page.getByTestId("dashboard-heading")).toHaveText("Live Factory Overview", { timeout: 20_000 });
  }

  async refreshData() {
    await this.page.getByRole("button", { name: /refresh data/i }).click();
  }
}
