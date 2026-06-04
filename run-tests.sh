#!/bin/bash
# Run tests inside the bot container

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Running tests in bot container...${NC}"
echo ""

# Run pytest in the bot container
# Set PYTHONPATH to include both /app (bot code) and /tests
docker compose exec bot env PYTHONPATH=/app:/tests pytest /tests "$@"

# Capture exit code
EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
else
    echo -e "${RED}✗ Tests failed with exit code $EXIT_CODE${NC}"
fi

exit $EXIT_CODE
