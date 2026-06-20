FROM python:3.13-slim

# Force python to flush output
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Create an unprivileged user to run the API (security review #7). The API only
# reads the bot_logs volume read-only and binds an unprivileged port, so a plain
# non-root USER is sufficient (no privilege-drop shim needed).
RUN groupadd --system app && useradd --system --gid app --home-dir /app app

# Install dependencies from the pinned lock for reproducible builds
# (security review #21). requirements.txt is kept as the human-edited intent.
COPY requirements.txt requirements.lock ./
RUN python -m pip install --no-cache-dir -r requirements.lock

# Copy application code
COPY . /app/api/

# Set PYTHONPATH so imports work
ENV PYTHONPATH=/app

# Drop to the unprivileged user for the runtime.
USER app

# Expose API port
EXPOSE 8000

# Start FastAPI via the launcher in api/main.py, which reads host/port/reload
# from settings. Reload is OFF by default and opt-in via API_RELOAD=true
# (security review #10) — no auto-reloader in prod or on a bare `docker run`.
CMD ["python", "-m", "api.main"]
