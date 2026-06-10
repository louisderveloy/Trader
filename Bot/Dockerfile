FROM python:3.13-slim

# Build argument to control dev dependencies installation
ARG INSTALL_DEV=false

# Force python to flush the out
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Copy requirements
COPY requirements.txt .
COPY requirements-dev.txt .

# Install system dependencies (PostgreSQL client for pg_isready healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
# In dev mode, install both regular and dev dependencies
# In prod mode, install only regular dependencies
RUN if [ "$INSTALL_DEV" = "true" ]; then \
        python -m pip install --no-cache-dir -r requirements-dev.txt; \
    else \
        python -m pip install --no-cache-dir -r requirements.txt; \
    fi

# Copy entrypoint script for database migrations
# Strip Windows CRLF line endings in case the file was checked out on Windows
COPY entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

COPY . .

# Use entrypoint script to run migrations before starting bot
ENTRYPOINT ["/entrypoint.sh"]