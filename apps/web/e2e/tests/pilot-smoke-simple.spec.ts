/// <reference types="node" />

// Simplified Pilot Smoke Test
// Uses ONLY getByRole() and getByPlaceholder() - NO data-testid

import { test, expect } from '@playwright/test';

test('Simplified Login + Dashboard Test', async ({ page }) => {
  // Go to login page
  await page.goto('/login');
  await page.waitForLoadState('networkidle');

  // Click "Sign Up" tab to create factory
  await page.getByRole('button', { name: /sign up/i }).click();
  await page.waitForTimeout(500);

  // Fill signup form using role-based selectors
  await page.getByRole('textbox', { name: /full name/i }).fill('Test Owner 42');
  await page.getByRole('textbox', { name: /email/i }).fill('test42@munshi-ai.example.com');
  
  // Phone field - use placeholder
  await page.getByPlaceholder(/phone|mobile/i).fill('+919****9942');
  
  await page.getByRole('textbox', { name: /factory name/i }).fill('Test Factory 42');
  
  // Password fields - use placeholder or role
  const passwordFields = await page.getByRole('textbox', { name: /password/i }).all();
  if (passwordFields.length >= 2) {
    await passwordFields[0].fill('Test@123456');
    await passwordFields[1].fill('Test@123456');
  } else {
    // If password fields are not found, use getByPlaceholder
    await page.getByPlaceholder(/password/i).first().fill('Test@123456');
    await page.getByPlaceholder(/confirm|re-enter/i).first().fill('Test@123456');
  }

  // Click Signup button
  await page.getByRole('button', { name: /sign up/i }).last().click();
  await page.waitForTimeout(3000);

  // Now try to login
  await page.getByRole('button', { name: /log in/i }).first().click();
  await page.waitForTimeout(500);

  // Fill login form
  await page.getByRole('textbox', { name: /email/i }).fill('test42@munshi-ai.example.com');
  await page.getByRole('textbox', { name: /password/i }).fill('Test@123456');

  // Click Login button
  await page.getByRole('button', { name: /log in/i }).last().click();

  // Wait for dashboard to load
  await page.waitForURL('**/dashboard', { timeout: 15000 });
  await page.waitForLoadState('networkidle');

  // ASSERTION: Dashboard heading exists (updated to match actual UI)
  await expect(page.getByRole('heading', { name: /Today's operational summary/i })).toBeVisible({ timeout: 5000 });
  console.log('SUCCESS: Login + Dashboard test passed!');
});
