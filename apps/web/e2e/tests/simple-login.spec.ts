import { test, expect } from '@playwright/test';

test('Simple Login Test', async ({ page }) => {
  // Navigate to login page
  await page.goto('/login');
  await page.waitForLoadState('networkidle');

  // Fill login form using robust label-based selectors
  await page.getByLabel('Email or Mobile Number').fill('test42@munshi-ai.example.com');
  await page.locator('[data-testid="staff-password-input"] input').fill('Test@123456');

  // Click login submit button using type=submit selector
  await page.locator('button[type="submit"]').click();

  // Wait for navigation to dashboard
  await page.waitForURL('**/dashboard', { timeout: 15000 });
  await page.waitForLoadState('networkidle');

  // ASSERTION: URL is /dashboard
  await expect(page).toHaveURL(/.*\/dashboard/);

  // ASSERTION: Dashboard loaded marker or dashboard greeting is visible
  await expect(page.getByTestId('dashboard-loaded').or(page.getByText("Today's operational summary"))).toBeVisible({ timeout: 10000 });
});
