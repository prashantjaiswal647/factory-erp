import { expect, type Page } from "@playwright/test";

type SignupData = {
  fullName: string;
  email: string;
  phone: string;
  password: string;
  factoryName: string;
};

export class SignupPage {
  constructor(private readonly page: Page) {}

  private form() {
    return this.page.locator("form").filter({ has: this.page.getByLabel("Full Name") });
  }

  async goto() {
    await this.page.goto("/login?tab=signup");
  }

  async expectVisible() {
    await expect(this.page.getByRole("heading", { name: "Create Owner Account" })).toBeVisible();
    await expect(this.page.getByLabel("Full Name")).toBeVisible();
    await expect(this.page.getByRole("combobox", { name: "Country code" })).toBeVisible();
    await expect(this.page.getByRole("textbox", { name: "Mobile Number" })).toBeVisible();
  }

  async expectIndiaDefault() {
    await expect(this.page.getByRole("combobox", { name: "Country code" })).toHaveValue("+91");
  }

  async submitEmpty() {
    await this.form().getByRole("button", { name: "Sign Up", exact: true }).click();
  }

  async fill(data: SignupData) {
    await this.page.getByLabel("Full Name").fill(data.fullName);
    await this.page.getByLabel("Email").fill(data.email);
    await this.page.getByRole("combobox", { name: "Country code" }).selectOption("+91");
    await this.page.getByRole("textbox", { name: "Mobile Number" }).fill(data.phone);
    await this.page.getByLabel("Factory Name").fill(data.factoryName);
    await this.page.getByLabel("Password", { exact: true }).fill(data.password);
    await this.page.getByLabel("Confirm Password", { exact: true }).fill(data.password);
  }

  async signup(data: SignupData) {
    await this.fill(data);
    await this.form().getByRole("button", { name: "Sign Up", exact: true }).click();
    await expect(this.page.getByText("Sign up successful")).toBeVisible({ timeout: 15_000 });
  }
}
