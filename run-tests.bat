@echo off
REM Run tests inside the bot container (Windows)

echo Running tests in bot container...
echo.

REM Run pytest in the bot container
REM Set PYTHONPATH to include both /app (bot code) and /tests
docker compose exec bot env PYTHONPATH=/app:/tests pytest /tests %*

REM Capture exit code
set EXIT_CODE=%ERRORLEVEL%

echo.
if %EXIT_CODE% EQU 0 (
    echo [32m✓ All tests passed![0m
) else (
    echo [31m✗ Tests failed with exit code %EXIT_CODE%[0m
)

exit /b %EXIT_CODE%
