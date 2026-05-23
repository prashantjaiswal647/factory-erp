# Staff Management Implementation Report

This report documents the design, architecture, security specifications, and verification results for the **Staff Management & Multi-Tenant Context Tracking** refactor implemented in Munshi AI ERP.

---

## 1. Backend Endpoints (Added/Changed)
All staff CRUD routes have been designed with strict multi-tenant boundary isolation. Rather than relying on frontend payloads, the logged-in user's identity is resolved dynamically on the backend to automatically scope all data filters.

*   `GET /api/v1/staff/list`
    *   **Access**: Owner-restricted.
    *   **Behavior**: Lists all staff members scoped to the current Owner's `factory_id` derived directly from their JWT session.
    *   **Zero UI Leakage**: Returns safe Pydantic models where `factory_id` is completely excluded from the payload, preventing leakages to frontend tables or state caches.
*   `POST /api/v1/staff/create`
    *   **Access**: Owner-restricted.
    *   **Behavior**: Instantly cryptographically hashes the password, commits the new staff user to the database, and automatically inherits the owner's active `factory_id` seamlessly. Newly created staff credentials instantly integrate with our OAuth2 token system.
*   `PUT /api/v1/staff/{staff_id}/update`
    *   **Access**: Owner-restricted.
    *   **Behavior**: Updates name, phone number, or role. Explicitly blocks cross-tenant operations (returns `403` or `404` if trying to access staff belonging to another factory).
*   `DELETE /api/v1/staff/{staff_id}/delete`
    *   **Access**: Owner-restricted.
    *   **Behavior**: Revokes system access for the target staff member. Performs dynamic multi-tenant checking.
*   `POST /api/v1/security/request-factory-id` & `POST /api/v1/security/verify-factory-id` (OTP Gateway)
    *   **Behavior**: Secure OTP dispatch and verification flows. Owners can verify their primary credentials to securely reveal their raw `factory_id` string on an on-demand audit panel.

---

## 2. Frontend Pages & Components (Changed)

### A. Staff Management Page (`apps/web/src/pages/StaffManagement.tsx`)
*   **Visual Registry Matrix**: A sleek, premium HTML table rendering Staff Name, Phone Number, Role, and Last Login Timestamp.
*   **Add Staff Member Form**: Clean input sections with validation for local phone formatting (`+91` defaults).
*   **Edit Staff Modal**: Includes slide overlay fields for updating staff info and an **Optional Password Reset** section for Owners to update credentials directly without providing the previous password.
*   **Delete Access Caution Modal**: A warning overlay requiring explicit confirmation before deleting/revoking a staff member's credentials.
*   **OTP Identity Audit Panel**: A floating auditor modal demonstrating secure workspace identity boundary audits.

### B. Password Input Component (`apps/web/src/components/PasswordInput.tsx`)
*   A reusable component implementing the **Show/Hide password visibility toggle** with custom icons (`lucide-react` eye assets) and standard accessibility properties (`aria-label`, `type="button"`).
*   Integrated across all password/credentials fields globally, including:
    *   Staff Creation & Confirmation password inputs.
    *   Staff Password Reset & Confirmation inputs inside the Edit Slider.
    *   Login & SignUp credentials input panels.
    *   Super Admin credentials input panels.
    *   Integrations Bot/Secret credentials input panels.

### C. Profile Page (`apps/web/src/pages/ProfilePage.tsx`)
*   Fully masked out `factory_id` visibly, replacing it with a user-friendly workspace tag.
*   Appended a secure self-password change panel requiring current password verification.

---

## 3. Zero UI Leakage Assertions
Strict multi-tenant security guidelines state that `factory_id` must remain backend-only. The following measures have been enforced:
1.  **Backend Data Stripping**: All staff Pydantic schemas explicitly strip/exclude `factory_id`.
2.  **Frontend Audit**: Verified that absolutely no UI elements, table headings, table cell data, button data-attributes, route names, or state cache indexes contain raw numeric or text values of `factory_id`.
3.  **Audit E2E Assertion**: Automated Playwright test utilizes dynamic regex filters `/factory[_\s-]?id/i` and page element scans to verify zero leakage across layout frames.

---

## 4. Verification Results & Command Sequence

### A. Automated Backend Tests
Unit tests were added in `apps/api/tests/test_staff_refactor.py` checking scope boundaries, instant password hashing, Zero Leakage responses, and OTP verification:
*   `test_staff_creation_hashes_instantly_and_inherits_factory` (Passed)
*   `test_staff_edit_and_delete_with_multi_tenant_boundaries` (Passed)
*   `test_otp_factory_id_extraction_gateway` (Passed)

### B. Playwright End-to-End Tests
E2E tests were written in `apps/web/e2e/tests/local/staff-flow.spec.ts` orchestrating:
*   **Step A**: Login as test Owner (with auto-registration fallback).
*   **Step B**: Navigate to Staff Management and assert zero leakage of `factory_id`.
*   **Step C**: Add new Supervisor staff with password toggle validations.
*   **Step D**: Verify inline registry updates and trigger inline Edit mutations.
*   **Step E**: Flush storage contexts.
*   **Step F**: Login as the newly created Supervisor and verify restricted view limits (Owner routes hidden).

### C. One-Command Local Verification Pipeline
Created a single, cross-platform PowerShell test runner `scripts/local-verify.ps1` with standard `$LASTEXITCODE` checks to ensure any build/test failure exits the script immediately. Mapped to `npm run verify:local` inside `apps/web/package.json`.

---

## 5. Known Limitations & TODOs
1.  **OTP flow is a Mock Gateway**: The OTP dispatch is mocked in backend logs/response payloads for current local demonstration.
2.  **Factory ID OTP Reveal**: Factory ID reveal requires future OTP SMS verification integration. Added TODO comment in the codebase.
