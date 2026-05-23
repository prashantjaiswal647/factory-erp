import { expect, type Page } from "@playwright/test";

export class LoginPage {
  constructor(private readonly page: Page) {}

  private form() {
    return this.page.locator("form").filter({ has: this.page.getByLabel("Email or Mobile Number") });
  }

  async goto() {
    await this.page.goto("/login");
  }

  async expectVisible() {
    await expect(this.page.getByRole("heading", { name: "Secure Login" })).toBeVisible();
    await expect(this.identifierField()).toBeVisible();
    await expect(this.page.getByLabel("Password", { exact: true })).toBeVisible();
  }

  async login(identifier: string, password: string) {
    await this.identifierField().fill(identifier);
    await this.page.getByLabel("Password", { exact: true }).fill(password);
    await this.form().getByRole("button", { name: "Login", exact: true }).click();
  }

  async expectAuthStorage() {
    const storage = await this.page.evaluate(() => ({
      aiToken: localStorage.getItem("ai_erp_token"),
      token: localStorage.getItem("token"),
      user: localStorage.getItem("ai_erp_user"),
      factoryId: localStorage.getItem("factory_id"),
    }));

    expect(storage.aiToken || storage.token).toBeTruthy();
    expect(storage.user).toBeTruthy();
    expect(storage.factoryId).toBeTruthy();
  }

  private identifierField() {
    return this.page.getByLabel("Email or Mobile Number").or(this.page.getByLabel("Phone Number")).or(this.page.getByLabel("Email"));
  }
}
