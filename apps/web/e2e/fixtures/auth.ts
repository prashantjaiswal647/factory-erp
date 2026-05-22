import { DashboardPage } from "../pages/DashboardPage";
import { LoginPage } from "../pages/LoginPage";
import { SignupPage } from "../pages/SignupPage";
import { uniqueLocalUser } from "./test-env";
import type { Page } from "@playwright/test";

export async function createAndLoginOwner(page: Page) {
  const user = uniqueLocalUser();
  const signup = new SignupPage(page);
  const login = new LoginPage(page);
  const dashboard = new DashboardPage(page);

  await signup.goto();
  await signup.signup(user);
  await login.login(user.phone, user.password);
  await dashboard.expectLoaded();

  return user;
}
