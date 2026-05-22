import { expect, type Page } from "@playwright/test";

export const ownerProtectedRoutes = [
  { path: "/dashboard", heading: "Live Factory Overview" },
  { path: "/profile", heading: "My Profile" },
  { path: "/inventory", heading: "Live Inventory" },
  { path: "/onboarding", heading: "Onboarding Wizard" },
  { path: "/machine-onboarding", heading: "Template Studio" },
  { path: "/calculator", heading: "Ideal vs Actual Cost Calculator" },
  { path: "/production", heading: "Production Entry" },
  { path: "/attendance", heading: "Attendance & Worker Ledger" },
  { path: "/customers", heading: "Customers" },
  { path: "/sales", heading: "Sales Entry" },
  { path: "/payments", heading: "Payment Collection" },
  { path: "/outstanding", heading: "Outstanding Udhaar" },
  { path: "/expenses", heading: "Factory Expenses" },
  { path: "/staff", heading: "Staff Management" },
  { path: "/integrations", heading: "Integrations" },
  { path: "/ai-supervisor", heading: "AI Supervisor" },
];

export class RouteTester {
  constructor(private readonly page: Page) {}

  async expectProtectedRouteOpens(route: { path: string; heading: string }) {
    await this.page.goto(route.path);
    await expect(this.page).toHaveURL(new RegExp(`${route.path.replace("/", "\\/")}$`));
    await expect(this.page.getByRole("heading", { name: route.heading })).toBeVisible({ timeout: 20_000 });
    await expect(this.page.getByText(/Payment Required|System Access Suspended|subscription has expired/i)).toHaveCount(0);
  }
}
