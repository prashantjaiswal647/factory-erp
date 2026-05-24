# local-verify.ps1

$ErrorActionPreference = "Stop"

Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "   Munshi AI ERP - Local Verification Suite   " -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Run Backend Refactor Unit Tests in Docker
Write-Host "[1/4] Executing Backend Multi-Tenant Refactor Unit Tests..." -ForegroundColor Yellow
try {
    docker exec -t ai-erp-system-api-1 python -m pytest tests/test_staff_refactor.py
    if ($LASTEXITCODE -ne 0) { throw "Backend unit tests failed" }
    Write-Host "[SUCCESS] Backend Unit Tests Passed!" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Backend Unit Tests Failed!" -ForegroundColor Red
    Exit 1
}

# Step 2: Build Frontend
Write-Host ""
Write-Host "[2/4] Verifying Frontend TypeScript Compilation and Build..." -ForegroundColor Yellow
try {
    Push-Location "apps/web"
    $OldEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    npm run build
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $OldEAP
    if ($exitCode -ne 0) { throw "Frontend build failed with exit code $exitCode" }
    Write-Host "[SUCCESS] Frontend Build Successful!" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Frontend Build Failed! $_" -ForegroundColor Red
    Pop-Location
    Exit 1
}

# Step 3: Run Playwright E2E Integration Tests
Write-Host ""
Write-Host "[3/4] Running Playwright E2E Staff & Worker Lifecycle Tests..." -ForegroundColor Yellow
try {
    $env:PLAYWRIGHT_ENABLE_STAFF_MUTATION_TESTS = "true"
    Write-Host "Running staff-flow spec..." -ForegroundColor Gray
    npx playwright test e2e/tests/local/staff-flow.spec.ts --workers=1
    if ($LASTEXITCODE -ne 0) { throw "Playwright staff-flow tests failed" }

    Write-Host "Running staff-worker-flow spec..." -ForegroundColor Gray
    npx playwright test e2e/tests/local/staff-worker-flow.spec.ts --workers=1
    if ($LASTEXITCODE -ne 0) { throw "Playwright staff-worker-flow tests failed" }

    Write-Host "Running worker-opening-attendance spec..." -ForegroundColor Gray
    npx playwright test e2e/tests/local/worker-opening-attendance.spec.ts --workers=1
    if ($LASTEXITCODE -ne 0) { throw "Playwright worker-opening-attendance tests failed" }

    Write-Host "[SUCCESS] Playwright E2E Staff & Worker Flow Integration Tests Passed!" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Playwright E2E Staff/Worker Flow Integration Tests Failed!" -ForegroundColor Red
    Pop-Location
    Exit 1
}

# Step 4: Run General E2E tests
Write-Host ""
Write-Host "[4/4] Running General Local E2E Test Suite and Auth Integrity Sweeps..." -ForegroundColor Yellow
try {
    Write-Host "Running general auth-flow tests..." -ForegroundColor Gray
    npx playwright test e2e/tests/local/auth-flow.spec.ts --workers=1
    if ($LASTEXITCODE -ne 0) { throw "Playwright auth-flow tests failed" }

    Write-Host "Running auth-integrity-check tests..." -ForegroundColor Gray
    npx playwright test e2e/tests/local/auth-integrity-check.spec.ts --workers=1
    if ($LASTEXITCODE -ne 0) { throw "Playwright auth-integrity-check tests failed" }

    Pop-Location
    Write-Host "[SUCCESS] All Local E2E Tests Completed Successfully!" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] General E2E/Integrity Tests Failed!" -ForegroundColor Red
    Pop-Location
    Exit 1
}

Write-Host ""
Write-Host "==============================================" -ForegroundColor Green
Write-Host " [OK] Local verification completed successfully! " -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Green

