@echo off
setlocal EnableExtensions

cd /d "%~dp0"

echo ==========================================
echo TestSprite preflight for AI ERP System
echo ==========================================
echo.

if not exist ".env.test" (
    echo ERROR: .env.test was not found.
    echo Create .env.test with TESTSPRITE_API_KEY=your_key before running this script.
    exit /b 1
)

for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env.test") do (
    if not "%%A"=="" (
        set "%%A=%%~B"
    )
)

if not defined TESTSPRITE_API_KEY (
    echo ERROR: TESTSPRITE_API_KEY is missing in .env.test.
    exit /b 1
)

for /f "tokens=1 delims=." %%A in ('node --version 2^>nul') do set "NODE_MAJOR=%%A"
set "NODE_MAJOR=%NODE_MAJOR:v=%"
if not defined NODE_MAJOR (
    echo ERROR: Node.js was not found on PATH. TestSprite MCP requires Node.js 22 or newer.
    exit /b 1
)
if %NODE_MAJOR% LSS 22 (
    echo ERROR: Node.js %NODE_MAJOR% detected. TestSprite MCP requires Node.js 22 or newer.
    exit /b 1
)
echo OK: Node.js is available.

echo.
echo Checking local ERP services...
curl.exe -s -f -o nul http://localhost:8000/openapi.json
if errorlevel 1 (
    echo ERROR: API is not reachable at http://localhost:8000/openapi.json.
    echo Start the stack with: docker compose up -d --build
    exit /b 1
)
echo OK: API OpenAPI spec is reachable.

curl.exe -s -f -o nul http://localhost:5173
if errorlevel 1 (
    echo ERROR: Frontend is not reachable at http://localhost:5173.
    echo Start the stack with: docker compose up -d --build
    exit /b 1
)
echo OK: Frontend is reachable.

echo.
echo Verifying TestSprite MCP package...
call npx -y @testsprite/testsprite-mcp@latest --version
if errorlevel 1 (
    echo ERROR: Could not run @testsprite/testsprite-mcp with npx.
    echo Check your internet connection, npm access, and TestSprite installation.
    exit /b 1
)

echo.
echo Preflight passed.
echo.
echo Next step:
echo 1. In Cursor or another MCP-capable IDE, configure TestSprite MCP with your API key.
echo 2. Use this prompt:
echo    Help me test this project with TestSprite. Test both frontend and backend. Use frontend URL http://localhost:5173, backend URL http://localhost:8000, OpenAPI spec http://localhost:8000/openapi.json, and PRD docs/testsprite-prd.md.
echo.
echo TestSprite documentation: https://docs.testsprite.com/mcp/getting-started/first-test
echo.

pause
