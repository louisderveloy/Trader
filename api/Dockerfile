FROM python:3.13-slim

# Force python to flush output
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Create an unprivileged user to run the API (security review #7). The API only
# reads the bot_logs volume read-only and binds an unprivileged port, so a plain
# non-root USER is sufficient (no privilege-drop shim needed).
RUN groupadd --system app && useradd --system --gid app --home-dir /app app

# Install dependencies
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /app/api/

# Set PYTHONPATH so imports work
ENV PYTHONPATH=/app

# Drop to the unprivileged user for the runtime.
USER app

# Expose API port
EXPOSE 8000

# Start FastAPI with uvicorn
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
