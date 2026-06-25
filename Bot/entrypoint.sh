#!/bin/bash
set -e

# --- Privilege drop (security review #7) ---------------------------------
# Start as root only long enough to guarantee the log volume is writable by
# 'app', then re-exec ourselves as the unprivileged user. The bot_logs named
# volume may pre-exist root-owned (created by older root images), so we chown
# it here — self-healing, no manual deploy step, no downtime if forgotten.
# Everything below the block runs as 'app'.
if [ "$(id -u)" = "0" ]; then
  mkdir -p /var/log/trader-bot
  chown -R app:app /var/log/trader-bot
  exec gosu app "$0" "$@"
fi

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
