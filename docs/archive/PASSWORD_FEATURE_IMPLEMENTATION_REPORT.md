# Password Features - Technical Implementation Report

This report summarizes the design, implementation, and verification of two secure, password-related SaaS features in **Munshi AI ERP**:
1. **Self-Password Change**: Any logged-in user can change their own password securely via their personal profile page.
2. **Global Password Visibility Toggle**: A highly accessible, secure visibility button integrated into all password inputs globally.

---

## 1. Backend Endpoint Implementation

### Route Mapping
- **Endpoint**: `PATCH /api/v1/profile/change-password`
- **Controller File**: `apps/api/auth.py`
- **Request Body Payload**:
  ```json
  {
    "current_password": "old_password_here",
    "new_password": "new_secure_password_here",
    "confirm_password": "new_secure_password_here",
    "user_id": null
  }
  ```

### Security Actions & Enforcements
1. **Bcrypt Hash Verification**: Uses the pre-configured bcrypt context helper (`verify_password`) to compare `current_password` with the user's stored hash.
2. **Password Strength Validation**: Enforces standard password policies: minimum 8 characters, at least one letter, and at least one number.
3. **Safe Database Audit Logging**: Logs the password mutation action in the `SuperAdminAuditLog` table. Plane text passwords and hashed passwords are strictly omitted:
   - `action_type`: `"CHANGE_PASSWORD"`
   - `entity_type`: `"user"`
   - `entity_id`: `str(current_user.id)`
   - `new_value`: `{"password_changed": true}`
4. **Data Isolation Boundaries**: Ensures regular users can only edit their own password context. The `user_id` parameter is restricted; if a non-Owner attempts to pass another user's ID, they receive a clean 403 Forbidden.

---

## 2. Frontend Component & Visials

### Reusable Password Toggle Input
- **Component File**: `apps/web/src/components/PasswordInput.tsx`
- **Interaction Model**: Encapsulates `showPassword` toggle hooks (`useState(false)`). Toggles raw input elements between `type="password"` and `type="text"`.
- **Accessibility & UX Enforcements**:
  - The toggle button uses `type="button"` to ensure it never interferes with parent form submissions.
  - Fully keyboard accessible (`tabIndex={0}`).
  - Dynamic accessibility labels (`aria-label="Show password"` / `"Hide password"`).
  - Built-in Tailwind layout and dynamic left icon rendering (`leftIcon={KeyRound}` used in Telegram bot integrations).
  - Explicit `data-testid="password-toggle"` for seamless automated testing.

### Global Field Migration Checklist
All password fields across the workspace have been refactored to use the new `<PasswordInput>` component:
1. **Factory Owner Onboarding Login Password** (`LoginPage.tsx`)
2. **Factory Owner Onboarding Sign Up Password** (`LoginPage.tsx`)
3. **Factory Owner Onboarding Confirm Password** (`LoginPage.tsx`)
4. **Self-Password Change Fields** (`ProfilePage.tsx` - Current, New, Confirm)
5. **Staff/Operator Account Password Creation Form** (`StaffManagement.tsx`)
6. **Super Admin Access Panel Login Password** (`SuperAdminPages.tsx`)
7. **Super Admin Create Factory Owner Password** (`SuperAdminPages.tsx`)
8. **Super Admin Create Factory Owner Confirm Password** (`SuperAdminPages.tsx`)
9. **Telegram Bot Token Field** (`Integrations.tsx`)

### Profile UI Layout Updates
- **File**: `apps/web/src/pages/ProfilePage.tsx`
- Added a dedicated card layout for **Change Password** directly below the personal details section, aligning with the zinc/neutral Tailwind design system.
- Integrates success alerts and validation summaries with `data-testid` properties.

---

## 3. Verification & Test Architecture

### E2E Playwright Tests
- **Spec File**: `apps/web/e2e/tests/local/staff-flow.spec.ts`
- Verifies that:
  - Password inputs are masked by default (`type="password"`).
  - Clicking the toggle button reveals the input value (`type="text"`).
  - Re-clicking masks the password correctly again.
  - Value remains fully consistent while toggling.
  - Integrates mutation guards using `PLAYWRIGHT_ENABLE_STAFF_MUTATION_TESTS` hooks.

### Backend Unit Tests
- **Spec File**: `apps/api/tests/test_staff_refactor.py`
  - Validates authentication layers, incorrect current password rejections (HTTP 400), password match/policy enforcements, and audit log generation.

---

## 4. Manual Verification Sequence

1. **Self-Password Change Verification**:
   - Log in as the Factory Owner, navigate to `/profile`, scroll to the "Change Password" card.
   - Enter an incorrect current password; verify the safety validation message: `"Current password is incorrect."`
   - Enter mismatching passwords; verify matching error toasts.
   - Enter a weak password; verify policy warning blocks.
   - Submit correct credentials, confirm the success banner, and verify logging out and logging back in with the new password works seamlessly.
2. **Visual Toggle Auditing**:
   - Navigate to `/login`, click the eye toggle on the password field, and ensure visibility acts correctly.
   - Navigate to `/staff-management` (as Owner), click the toggle on the creation fields, and verify consistency.
