FROM python:3.13-slim

# Build argument to control dev dependencies installation
ARG INSTALL_DEV=false

# Force python to flush the out
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Copy requirements
COPY requirements.txt .
COPY requirements-dev.txt .

# Install dependencies
# In dev mode, install both regular and dev dependencies
# In prod mode, install only regular dependencies
RUN if [ "$INSTALL_DEV" = "true" ]; then \
        python -m pip install --no-cache-dir -r requirements-dev.txt; \
    else \
        python -m pip install --no-cache-dir -r requirements.txt; \
    fi

COPY . .

# Use docker_entry command as entrypoint to keep container alive
ENTRYPOINT [ "python", "-m", "main", "docker_entry" ]