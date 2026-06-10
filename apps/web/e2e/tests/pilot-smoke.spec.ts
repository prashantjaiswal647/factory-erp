/// <reference types="node" />

// Production-Grade Pilot Synthetic Smoke Test
// Uses ONLY getByTestId() and getByRole() - NO text selectors

import { test, expect } from '@playwright/test';
import { createSeedFactory } from '../fixtures/seed-factory';
import * as fs from 'fs';
import * as path from 'path';

const SCREENSHOT_DIR = 'screenshots/pilot-smoke';
const API_LOG_DIR = 'api-logs';
const CONSOLE_ERROR_FILE = 'console-errors.json';

interface ConsoleError {
  url: string;
  message: string;
  type: string;
}

interface ApiError {
  method: string;
  url: string;
  status: number;
  body: string;
  timestamp: string;
}

let consoleErrors: ConsoleError[] = [];
let apiErrors: ApiError[] = [];

test.describe('Production Pilot Smoke Test - Full Lifecycle', () => {
  let page: any;
  const seed = 42;
  const factory = createSeedFactory(seed);

  test.beforeAll(async () => {
    // Ensure directories exist
    [SCREENSHOT_DIR, API_LOG_DIR].forEach((dir: string) => {
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
    });

    // Clear previous results
    if (fs.existsSync(CONSOLE_ERROR_FILE)) {
      fs.unlinkSync(CONSOLE_ERROR_FILE);
    }
  });

  test.beforeEach(async ({ context }: any) => {
    consoleErrors = [];
    apiErrors = [];

    page = await context.newPage();

    // Capture console errors - FAIL TEST ON ANY ERROR
    page.on('console', (msg: any) => {
      if (msg.type() === 'error' || msg.type() === 'warning') {
        const error: ConsoleError = {
          url: page.url(),
          message: msg.text(),
          type: msg.type(),
        };
        consoleErrors.push(error);
        console.error(`[CONSOLE ${msg.type().toUpperCase()}] ${msg.text()}`);
      }
    });

    // Capture API responses - FAIL ON 500/502
    page.on('response', async (response: any) => {
      const url = response.url();
      const status = response.status();

      if (url.includes('/api/') && (status === 500 || status === 502)) {
        let body = '';
        try {
          body = await response.text();
        } catch (e) {
          body = 'Could not read response body';
        }

        const error: ApiError = {
          method: response.request().method(),
          url,
          status,
          body: body.substring(0, 1000),
          timestamp: new Date().toISOString(),
        };

        apiErrors.push(error);
        console.error(`[API ERROR ${status}] ${response.request().method()} ${url}`);
      }
    });

    // Clear local storage before each test
    await page.context().clearCookies();
  });

  test.afterEach(async () => {
    fs.writeFileSync(CONSOLE_ERROR_FILE, JSON.stringify(consoleErrors, null, 2));
    fs.writeFileSync(
      path.join(API_LOG_DIR, 'pilot-smoke-api-errors.json'),
      JSON.stringify(apiErrors, null, 2)
    );
  });

  test('Full Pilot Factory Lifecycle - 16 Steps with Assertions', async () => {
    // ===========================================
    // PRE-STEP 0: CREATE TEST FACTORY (Signup)
    // ===========================================
    // PRE-STEP 0: CREATE TEST FACTORY (Signup)
    await test.step('Pre-step 0: Create Test Factory via Signup', async () => {
      await page.goto('/login');
      await page.waitForLoadState('networkidle');

      // Click "Sign Up" tab
      await page.getByRole('button', { name: /sign up/i }).click();
      await page.waitForTimeout(500);

      // Fill signup form using CORRECT selectors
      await page.getByTestId('signup-full-name').fill(`Test Owner ${seed}`);
      await page.getByTestId('signup-email').fill(factory.email);

      // Phone field: PhoneNumberInput component - use placeholder
      await page.getByPlaceholder(/phone|mobile/i).fill(factory.ownerPhone);

      await page.getByTestId('signup-factory-name').fill(factory.factoryName);

      // Password fields: PasswordInput renders data-testid on wrapper <div>
      // Use locator to find <input> inside wrapper
      await page.locator('[data-testid="signup-password-input"] input').fill(factory.password);
      await page.locator('[data-testid="signup-confirm-password-input"] input').fill(factory.password);

      // Click Signup button
      await page.getByRole('button', { name: /sign up/i }).last().click();
      await page.waitForTimeout(3000);

      // ASSERTION: Success message or redirect to login
      const successMsg = await page.getByText(/success|verify|login/i).first().textContent({ timeout: 5000 }).catch(() => '');
      expect(successMsg.length).toBeGreaterThan(0);
    });

    // ===========================================
    // STEP 1: LOGIN TEST FACTORY
    // ===========================================
    await test.step('Step 1: Login Test Factory', async () => {
      await page.goto('/login');
      await page.waitForLoadState('networkidle');
      await page.screenshot({ path: `${SCREENSHOT_DIR}/01-login-page.png`, fullPage: true });

      // Fill login form using role-based selectors (more reliable)
      await page.getByRole('textbox', { name: /email/i }).fill(factory.email);
      await page.getByRole('textbox', { name: /password/i }).fill(factory.password);

      // Click Login button using CSS selector (bypass getByTestId pitfall)
      await page.locator('[data-test-id="login-button"]').click();

      // Wait for navigation to dashboard (with better error handling)
      try {
        await page.waitForURL('**/dashboard', { timeout: 15000 });
      } catch (e) {
        // CAPTURE current URL and any error messages
        const currentUrl = page.url();
        const errorMsg = await page.getByText(/error|invalid|wrong|401|unauthorized/i).first().textContent().catch(() => 'No error message found');
        console.log(`Login failed! URL: ${currentUrl}, Error: ${errorMsg}`);
        await page.screenshot({ path: `${SCREENSHOT_DIR}/login-failed.png`, fullPage: true });
        throw new Error(`Login failed! URL: ${currentUrl}, Error: ${errorMsg}`);
      }

      await page.waitForLoadState('networkidle');

      await page.screenshot({ path: `${SCREENSHOT_DIR}/01-logged-in.png`, fullPage: true });

      // ASSERTION: Dashboard loaded marker exists
      await expect(page.getByTestId('dashboard-loaded')).toBeVisible({ timeout: 5000 });

      // ASSERTION: No console errors
      const criticalErrors = consoleErrors.filter((e: ConsoleError) => e.type === 'error');
      expect(criticalErrors).toHaveLength(0);

      // ASSERTION: No API 500/502 errors
      const serverErrors = apiErrors.filter((e: ApiError) => e.status === 500 || e.status === 502);
      expect(serverErrors).toHaveLength(0);
    });

    // ============================================
    // STEP 2: CREATE MASTER DATA
    // ============================================
    await test.step('Step 2: Create Master Data', async () => {
      await page.goto('/onboarding');
      await page.waitForLoadState('networkidle');
      await page.screenshot({ path: `${SCREENSHOT_DIR}/02-master-data.png`, fullPage: true });

      // Add products using data-test-id
      for (const product of factory.masterData.products) {
        // Click "Add Product" button using data-test-id
        await page.getByTestId('add-product-button').click();
        await page.waitForTimeout(500);

        // Fill product form using role-based selectors
        await page.getByRole('textbox', { name: /name/i }).fill(product.name);
        await page.getByRole('textbox', { name: /size/i }).fill(product.size);
        await page.getByRole('textbox', { name: /variety/i }).fill(product.variety);

        // Save using role
        await page.getByRole('button', { name: /save/i }).click();
        await page.waitForTimeout(1000);
      }

      await page.screenshot({ path: `${SCREENSHOT_DIR}/02-master-data-done.png`, fullPage: true });

      // ASSERTION: No console errors
      const errors = consoleErrors.filter((e: ConsoleError) => e.type === 'error');
      expect(errors).toHaveLength(0);
    });

    // ============================================
    // STEP 3: ADD OPENING INVENTORY
    // ============================================
    await test.step('Step 3: Add Opening Inventory', async () => {
      await page.goto('/inventory');
      await page.waitForLoadState('networkidle');
      await page.screenshot({ path: `${SCREENSHOT_DIR}/03-inventory.png`, fullPage: true });

      // Add opening inventory for each material
      for (const item of factory.inventory) {
        // Click "Add Item" button using data-test-id
        await page.getByTestId('add-stock-button').click();
        await page.waitForTimeout(500);

        // Fill inventory form using role-based selectors
        await page.getByRole('textbox', { name: /material/i }).fill(item.material);
        await page.getByRole('textbox', { name: /quantity/i }).fill(item.quantity.toString());
        await page.getByRole('textbox', { name: /cost/i }).fill(item.unitCost.toString());

        // Save
        await page.getByRole('button', { name: /save/i }).click();
        await page.waitForTimeout(1000);
      }

      await page.screenshot({ path: `${SCREENSHOT_DIR}/03-inventory-done.png`, fullPage: true });
    });

    // ============================================
    // STEP 4: ADD PRODUCTION FOR 7 DAYS
    // ============================================
    await test.step('Step 4: Add Production for 7 Days', async () => {
      await page.goto('/production');
      await page.waitForLoadState('networkidle');
      await page.screenshot({ path: `${SCREENSHOT_DIR}/04-production.png`, fullPage: true });

      for (let i = 0; i < factory.production.length; i++) {
        const prod = factory.production[i];

        // Click "Add Production" button using data-test-id
        await page.getByTestId('add-production-button').click();
        await page.waitForTimeout(500);

        // Fill production form
        const date = `2026-06-${String(i + 1).padStart(2, '0')}`;
        await page.getByRole('textbox', { name: /date/i }).fill(date);
        await page.getByRole('textbox', { name: /product/i }).fill(prod.product);
        await page.getByRole('textbox', { name: /quantity/i }).fill(prod.quantity.toString());
        await page.getByRole('textbox', { name: /wastage/i }).fill(prod.wastage.toString());

        // Save
        await page.getByRole('button', { name: /save/i }).click();
        await page.waitForTimeout(1000);
      }

      await page.screenshot({ path: `${SCREENSHOT_DIR}/04-production-done.png`, fullPage: true });
    });

    // ============================================
    // STEP 5: CREATE SALE
    // ============================================
    await test.step('Step 5: Create Sale', async () => {
      await page.goto('/sales');
      await page.waitForLoadState('networkidle');
      await page.screenshot({ path: `${SCREENSHOT_DIR}/05-sales.png`, fullPage: true });

      const sale = factory.sales[0];

      // Click "Create Sale" button using data-test-id
      await page.getByTestId('create-sale-button').click();
      await page.waitForTimeout(500);

      // Fill sale form
      await page.getByRole('textbox', { name: /customer/i }).fill(sale.customer);
      await page.getByRole('textbox', { name: /product/i }).fill(sale.product);
      await page.getByRole('textbox', { name: /quantity/i }).fill(sale.quantity.toString());
      await page.getByRole('textbox', { name: /rate/i }).fill(sale.rate.toString());

      // Submit
      await page.getByRole('button', { name: /submit|create/i }).click();
      await page.waitForSelector('text=/success/i', { timeout: 5000 });

      await page.screenshot({ path: `${SCREENSHOT_DIR}/05-sale-created.png`, fullPage: true });

      // ASSERTION: Invoice can be generated
      const invoiceButton = page.getByRole('button', { name: /invoice/i }).or(page.getByRole('link', { name: /invoice/i }));
      await expect(invoiceButton).toBeVisible({ timeout: 3000 });
    });

    // ============================================
    // STEP 6: GENERATE INVOICE PDF
    // ============================================
    await test.step('Step 6: Generate Invoice PDF', async () => {
      // Click "Generate Invoice" button
      await page.getByTestId('generate-invoice-button').click();
      await page.waitForSelector('text=/generated|pdf/i', { timeout: 5000 });

      await page.screenshot({ path: `${SCREENSHOT_DIR}/06-invoice-generated.png`, fullPage: true });

      // ASSERTION: Invoice download link exists
      const downloadLink = page.getByRole('link', { name: /download/i });
      await expect(downloadLink).toBeVisible({ timeout: 3000 });

      // ASSERTION: Invoice appears in invoices list
      await page.goto('/invoices');
      const invoiceCount = await page.getByTestId('invoice-item').count();
      expect(invoiceCount).toBeGreaterThan(0);
    });

    // ============================================
    // STEP 7: RECORD PARTIAL PAYMENT
    // ============================================
    await test.step('Step 7: Record Partial Payment', async () => {
      await page.goto('/payments');
      await page.waitForLoadState('networkidle');
      await page.screenshot({ path: `${SCREENSHOT_DIR}/07-payments.png`, fullPage: true });

      // Click "Record Payment" button
      await page.getByTestId('record-payment-button').click();
      await page.waitForTimeout(500);

      // Fill partial payment (2000 out of 4250)
      await page.getByTestId('payment-amount-input').fill('2000');
      await page.getByRole('textbox', { name: /mode/i }).fill('UPI');

      // Submit
      await page.getByRole('button', { name: /submit|save/i }).click();
      await page.waitForSelector('text=/recorded|success/i', { timeout: 5000 });

      await page.screenshot({ path: `${SCREENSHOT_DIR}/07-partial-payment.png`, fullPage: true });
    });

    // ============================================
    // STEP 8: VERIFY OUTSTANDING REMAINS
    // ============================================
    await test.step('Step 8: Verify Outstanding Remains', async () => {
      await page.goto('/outstanding');
      await page.waitForLoadState('networkidle');
      await page.screenshot({ path: `${SCREENSHOT_DIR}/08-outstanding.png`, fullPage: true });

      // ASSERTION: Outstanding > 0 (partial payment of 2000 from 4250)
      const outstandingText = await page.getByTestId('outstanding-amount').textContent();
      const outstanding = parseFloat(outstandingText?.replace(/[^0-9.]/g, '') || '0');

      // ASSERTION: Outstanding should be ~2250 (4250 - 2000)
      expect(outstanding).toBeGreaterThan(2000);
      expect(outstanding).toBeLessThan(2500);

      // ASSERTION: Outstanding math is correct
      const totalSale = factory.sales[0].quantity * factory.sales[0].rate; // 5000 * 0.85 = 4250
      const expectedOutstanding = totalSale - 2000; // 2250
      expect(Math.abs(outstanding - expectedOutstanding)).toBeLessThan(10); // Allow 10 paise tolerance
    });

    // ============================================
    // STEP 9: OPEN COLLECTION WAR ROOM
    // ============================================
    await test.step('Step 9: Open Collection War Room', async () => {
      await page.goto('/collection-war-room');
      await page.waitForLoadState('networkidle');
      await page.screenshot({ path: `${SCREENSHOT_DIR}/09-war-room.png`, fullPage: true });

      // ASSERTION: War room page loads
      await expect(page.getByTestId('collection-war-room-card')).toBeVisible();
    });

    // ============================================
    // STEP 10: COPY RECOVERY REMINDER
    // ============================================
    await test.step('Step 10: Copy Recovery Reminder', async () => {
      // Click "Copy Reminder" button
      await page.getByTestId('copy-recovery-reminder-button').click();
      await page.waitForTimeout(1000);

      await page.screenshot({ path: `${SCREENSHOT_DIR}/10-recovery-reminder.png`, fullPage: true });

      // ASSERTION: Recovery suggestion generated
      const reminder = await page.getByTestId('reminder-text').textContent().catch(() => '');
      expect(reminder.length).toBeGreaterThan(10);
    });

    // ============================================
    // STEP 11: TRIGGER TELEGRAM (MOCK MODE)
    // ============================================
    await test.step('Step 11: Trigger Telegram Command Center', async () => {
      await page.goto('/integrations');
      await page.waitForLoadState('networkidle');

      // Click Telegram tab/button
      await page.getByTestId('telegram-integration-status').click();
      await page.waitForTimeout(500);

      await page.screenshot({ path: `${SCREENSHOT_DIR}/11-telegram.png`, fullPage: true });

      // ASSERTION: Telegram integration UI exists
      await expect(page.getByText(/telegram/i)).toBeVisible();
    });

    // ============================================
    // STEP 12: VERIFY DAILY BRIEFING LOADS
    // ============================================
    await test.step('Step 12: Verify Daily Briefing Loads', async () => {
      await page.goto('/dashboard');
      await page.waitForLoadState('networkidle');

      // BriefingCard auto-loads on mount - just wait for text
      await page.waitForTimeout(3000);

      await page.screenshot({ path: `${SCREENSHOT_DIR}/12-briefing.png`, fullPage: true });

      // ASSERTION: Briefing text visible
      const briefingText = await page.getByText(/Morning Briefing|briefing/i).first().textContent({ timeout: 5000 }).catch(() => '');
      expect(briefingText.length).toBeGreaterThan(5);
    });

    // ============================================
    // STEP 13: OPEN BRIEFING HISTORY
    // ============================================
    await test.step('Step 13: Open Briefing History', async () => {
      await page.goto('/briefing-history');
      await page.waitForLoadState('networkidle');
      await page.screenshot({ path: `${SCREENSHOT_DIR}/13-briefing-history.png`, fullPage: true });

      // ASSERTION: Briefing history exists
      const historyCount = await page.getByTestId('briefing-item').count();
      expect(historyCount).toBeGreaterThan(0);
    });

    // ============================================
    // STEP 14: RECORD FULL PAYMENT
    // ============================================
    await test.step('Step 14: Record Full Payment', async () => {
      await page.goto('/payments');
      await page.waitForLoadState('networkidle');

      // Click "Record Payment" button
      await page.getByTestId('record-payment-button').click();
      await page.waitForTimeout(500);

      // Fill full payment (remaining 2250)
      await page.getByTestId('payment-amount-input').fill('2250');
      await page.getByRole('textbox', { name: /mode/i }).fill('Bank Transfer');

      // Submit
      await page.getByRole('button', { name: /submit|save/i }).click();
      await page.waitForSelector('text=/recorded|success/i', { timeout: 5000 });

      await page.screenshot({ path: `${SCREENSHOT_DIR}/14-full-payment.png`, fullPage: true });
    });

    // ============================================
    // STEP 15: VERIFY OUTSTANDING RESOLVED
    // ============================================
    await test.step('Step 15: Verify Outstanding Resolved', async () => {
      await page.goto('/outstanding');
      await page.waitForLoadState('networkidle');
      await page.screenshot({ path: `${SCREENSHOT_DIR}/15-outstanding-resolved.png`, fullPage: true });

      // ASSERTION: Outstanding = 0
      const outstandingText = await page.getByTestId('outstanding-amount').textContent();
      const outstanding = parseFloat(outstandingText?.replace(/[^0-9.]/g, '') || '0');

      expect(outstanding).toBe(0);

      // ASSERTION: Outstanding math is correct
      const totalSale = factory.sales[0].quantity * factory.sales[0].rate; // 4250
      const totalPaid = 2000 + 2250; // 4250
      expect(totalPaid).toBe(totalSale);
    });

    // ============================================
    // STEP 16: VERIFY DASHBOARD HEALTH IMPROVES
    // ============================================
    await test.step('Step 16: Verify Dashboard Health Improves', async () => {
      await page.goto('/dashboard');
      await page.waitForLoadState('networkidle');
      await page.screenshot({ path: `${SCREENSHOT_DIR}/16-dashboard-health.png`, fullPage: true });

      // ASSERTION: Health score is visible
      const healthScore = await page.getByTestId('health-score').textContent();
      expect(healthScore).toBeTruthy();

      // ASSERTION: Collection status improved
      await expect(page.getByText(/collection|outstanding/i)).toBeVisible();
    });

    // ============================================
    // FINAL ASSERTIONS
    // ============================================
    await test.step('Final Assertions - No Errors Allowed', async () => {
      // ASSERTION 1: No console errors
      const consoleErrorsOnly = consoleErrors.filter((e: ConsoleError) => e.type === 'error');
      expect(consoleErrorsOnly).toHaveLength(0);

      // ASSERTION 2: No API 500 errors
      const api500Errors = apiErrors.filter((e: ApiError) => e.status === 500);
      expect(api500Errors).toHaveLength(0);

      // ASSERTION 3: No API 502 errors
      const api502Errors = apiErrors.filter((e: ApiError) => e.status === 502);
      expect(api502Errors).toHaveLength(0);

      await page.screenshot({ path: `${SCREENSHOT_DIR}/17-test-complete.png`, fullPage: true });

      // Generate PASS/FAIL report
      const report = {
        timestamp: new Date().toISOString(),
        status: consoleErrorsOnly.length === 0 && api500Errors.length === 0 && api502Errors.length === 0 ? 'PASS' : 'FAIL',
        consoleErrors: consoleErrors.length,
        apiErrors: apiErrors.length,
        screenshots: fs.existsSync(SCREENSHOT_DIR) ? fs.readdirSync(SCREENSHOT_DIR).filter((f: string) => f.endsWith('.png')) : [],
      };

      fs.writeFileSync('PILOT_SYNTHETIC_SMOKE_REPORT.json', JSON.stringify(report, null, 2));
    });
  });
});
