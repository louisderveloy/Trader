FROM python:3.13-slim

# Build argument to control dev dependencies installation
ARG INSTALL_DEV=false

# Force python to flush the out
ENV PYTHONUNBUFFERED=1
# alembic imports migration modules from the host-owned /db mount; don't write
# .pyc there (the unprivileged 'app' user can't, and it's noise anyway).
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Copy requirements
COPY requirements.txt .
COPY requirements-dev.txt .

# System deps: postgresql-client (pg_isready healthcheck), gosu (drop root->app
# in the entrypoint). Also create the unprivileged 'app' user (security review #7).
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client gosu \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app && useradd --system --gid app --home-dir /app app

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

# Pre-create + own the log dir so a fresh named volume inherits 'app' ownership.
# (An existing root-owned volume is self-healed by the entrypoint chown.)
RUN mkdir -p /var/log/trader-bot && chown -R app:app /var/log/trader-bot

# Entrypoint runs migrations then the bot. It starts as root only to chown the
# log volume, then re-execs as 'app' via gosu (no USER directive on purpose).
ENTRYPOINT ["/entrypoint.sh"]