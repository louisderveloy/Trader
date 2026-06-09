#!/bin/bash
set -e

echo "=== Bot Startup: Database Migration ==="

# Wait for PostgreSQL
echo "Waiting for PostgreSQL..."
while ! pg_isready -h postgres -p 5432 -U "${POSTGRES_USER:-trader}"; do
  sleep 1
done
echo "PostgreSQL is ready!"

# Run migrations
echo "Running Alembic migrations..."
cd /db
alembic upgrade head

if [ $? -eq 0 ]; then
  echo "Migrations completed successfully!"
else
  echo "Migration failed! Exiting..."
  exit 1
fi

# Start bot
echo "Starting trading bot..."
cd /app
exec python -m main docker_entry "$@"
