# Development vs Production Architecture

**Last updated:** 2026-06-03 (Phase 2)

---

## Overview

The trading bot has **two distinct deployment modes** with different architectures:

1. **Development** (`docker-compose.yml`) — Direct port access, no Traefik
2. **Production** (`docker-compose.prod.yml`) — Traefik reverse proxy with HTTPS

---

## Development Architecture

### Network Topology

```
┌─────────────────────────────────────────────────────────┐
│                    localhost (127.0.0.1)                │
└─────────────────────────────────────────────────────────┘
         │                   │                   │
    Port 5173          Port 8000          Port 3000
         │                   │                   │
    Dashboard              API              Grafana
    (Vue.js)           (FastAPI)        (visualization)
                            │
                       Redis pub/sub
                            │
                        Bot Python
                            │
                 PostgreSQL + TimescaleDB
```

### Service Access

| Service | URL | Port | Purpose |
|---------|-----|------|---------|
| **Dashboard** | http://localhost:5173 | 5173 | Vue.js frontend |
| **API** | http://localhost:8000 | 8000 | FastAPI backend |
| **Grafana** | http://localhost:3000 | 3000 | Visualization |
| **PostgreSQL** | localhost:5432 | 5432 | Database (direct access) |
| **Redis** | localhost:6379 | 6379 | Cache/messaging (direct access) |

### Key Features

✅ **No Traefik** — Simpler setup, direct access
✅ **No HTTPS** — Uses HTTP for local development
✅ **Hot Reload** — Code changes reflect immediately
✅ **Direct Ports** — Easy debugging with browser dev tools
✅ **Single Worker** — API runs with 1 worker for easier debugging

### Environment Variables (.env)

```bash
# Service URLs
VITE_API_BASE_URL=http://localhost:8000
VITE_GRAFANA_BASE_URL=http://localhost:3000
GF_SERVER_ROOT_URL=http://localhost:3000

# Development flags
ENVIRONMENT=dev
DEBUG=true
HOT_RELOAD=true
API_RELOAD=true
API_WORKERS=1

# Binance testnet
BINANCE_TESTNET=true
BINANCE_TESTNET_API_KEY=your_testnet_key
BINANCE_TESTNET_API_SECRET=your_testnet_secret
```

### Docker Compose

**File:** `docker-compose.yml`

```yaml
services:
  dashboard:
    ports:
      - "5173:5173"  # Direct access
    environment:
      VITE_API_BASE_URL: http://localhost:8000

  api:
    ports:
      - "8000:8000"  # Direct access
    environment:
      API_RELOAD: true
      API_WORKERS: 1

  grafana:
    ports:
      - "3000:3000"  # Direct access
    environment:
      GF_SERVER_ROOT_URL: http://localhost:3000
      GRAFANA_AUTH_ANONYMOUS_ENABLED: false

  # No Traefik service in development
```

### Starting Development Environment

```bash
# 1. Copy and configure .env
cp .env.example .env
nano .env  # Set BINANCE_TESTNET_API_KEY, etc.

# 2. Start services
docker-compose up -d

# 3. Access services
# Dashboard: http://localhost:5173
# API: http://localhost:8000
# Grafana: http://localhost:3000
```

---

## Production Architecture

### Network Topology

```
┌─────────────────────────────────────────────────────────────────┐
│                  Traefik (reverse proxy + HTTPS)                │
│       ForwardAuth JWT → unified auth for Vue.js + Grafana       │
└────────────┬───────────────────┬───────────────────┬────────────┘
             │                   │                   │
    bot.yourdomain.com   api.yourdomain.com   grafana.yourdomain.com
         (HTTPS)              (HTTPS)              (HTTPS)
             │                   │                   │
        Dashboard               API              Grafana
        (Vue.js)            (FastAPI)        (visualization)
                                 │
                            Redis pub/sub
                                 │
                             Bot Python
                                 │
                      PostgreSQL + TimescaleDB
```

### Service Access

| Service | URL | Exposed Port | Purpose |
|---------|-----|--------------|---------|
| **Dashboard** | https://bot.yourdomain.com | None (via Traefik) | Vue.js frontend |
| **API** | https://api.yourdomain.com | None (via Traefik) | FastAPI backend |
| **Grafana** | https://grafana.yourdomain.com | None (via Traefik) | Visualization |
| **PostgreSQL** | Internal only | None | Database |
| **Redis** | Internal only | None | Cache/messaging |
| **Traefik** | — | 80, 443, 8080 | Reverse proxy |

### Key Features

✅ **Traefik Reverse Proxy** — Single entry point
✅ **HTTPS** — Let's Encrypt automatic certificates
✅ **JWT Auth** — ForwardAuth middleware for unified auth
✅ **No Direct Ports** — Services not exposed, only via Traefik
✅ **Multiple Workers** — API runs with 4+ workers
✅ **Named Volumes** — Docker-managed persistent data

### Environment Variables (.env)

```bash
# Service URLs (domains)
DOMAIN_DASHBOARD=bot.yourdomain.com
DOMAIN_API=api.yourdomain.com
DOMAIN_GRAFANA=grafana.yourdomain.com
ACME_EMAIL=your-email@example.com

# Dashboard URLs (via Traefik)
VITE_API_BASE_URL=https://api.yourdomain.com
VITE_GRAFANA_BASE_URL=https://grafana.yourdomain.com

# Production flags
ENVIRONMENT=prod
DEBUG=false
HOT_RELOAD=false
API_RELOAD=false
API_WORKERS=4

# Binance mainnet
BINANCE_TESTNET=false
BINANCE_MAINNET_API_KEY=your_mainnet_key
BINANCE_MAINNET_API_SECRET=your_mainnet_secret

# Security
JWT_SECRET_KEY=generate_with_openssl_rand_hex_32
POSTGRES_PASSWORD=strong_random_password
GRAFANA_ADMIN_PASSWORD=strong_random_password
```

### Docker Compose

**File:** `docker-compose.prod.yml`

```yaml
services:
  traefik:
    image: traefik:v3.0
    command:
      - "--certificatesresolvers.letsencrypt.acme.email=${ACME_EMAIL}"
      - "--entrypoints.websecure.http.tls.certresolver=letsencrypt"
    ports:
      - "80:80"
      - "443:443"
      - "8080:8080"  # Dashboard

  dashboard:
    # No ports exposed (via Traefik only)
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.dashboard.rule=Host(`${DOMAIN_DASHBOARD}`)"
      - "traefik.http.routers.dashboard.tls.certresolver=letsencrypt"

  api:
    # No ports exposed
    environment:
      API_RELOAD: false
      API_WORKERS: 4
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.api.rule=Host(`${DOMAIN_API}`)"

  grafana:
    # No ports exposed
    environment:
      GF_SERVER_ROOT_URL: https://${DOMAIN_GRAFANA}
      GRAFANA_AUTH_ANONYMOUS_ENABLED: true  # Behind ForwardAuth
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.grafana.rule=Host(`${DOMAIN_GRAFANA}`)"
```

### Starting Production Environment

```bash
# 1. On VPS, configure .env for production
nano .env
# - Set ENVIRONMENT=prod
# - Set BINANCE_TESTNET=false
# - Configure domains
# - Change all passwords!

# 2. Start with production compose file
docker-compose -f docker-compose.prod.yml up -d

# 3. Access services via domains
# Dashboard: https://bot.yourdomain.com
# API: https://api.yourdomain.com
# Grafana: https://grafana.yourdomain.com
```

---

## Key Differences Summary

| Aspect | Development | Production |
|--------|-------------|------------|
| **Compose File** | `docker-compose.yml` | `docker-compose.prod.yml` |
| **Reverse Proxy** | ❌ None | ✅ Traefik |
| **HTTPS** | ❌ HTTP only | ✅ Let's Encrypt |
| **Ports** | ✅ Direct (5173, 8000, 3000) | ❌ None (via Traefik) |
| **URLs** | `localhost:PORT` | `service.yourdomain.com` |
| **Hot Reload** | ✅ Enabled | ❌ Disabled |
| **API Workers** | 1 | 4+ |
| **Exchange** | Testnet | Mainnet |
| **Volumes** | Bind mounts (except PostgreSQL) | Named volumes |
| **Auth** | Direct Grafana login | JWT + ForwardAuth |
| **Debugging** | ✅ Easy (direct access) | ⚠️ Harder (via proxy) |

---

## Migration Path: Dev → Prod

When ready to deploy to production:

1. **Prepare VPS:**
   - Ubuntu/Debian server
   - Docker + Docker Compose installed
   - DNS records pointing to VPS IP

2. **Configure .env:**
   ```bash
   # Change environment
   ENVIRONMENT=prod

   # Switch to mainnet
   BINANCE_TESTNET=false
   BINANCE_MAINNET_API_KEY=...
   BINANCE_MAINNET_API_SECRET=...

   # Set domains
   DOMAIN_DASHBOARD=bot.yourdomain.com
   DOMAIN_API=api.yourdomain.com
   DOMAIN_GRAFANA=grafana.yourdomain.com
   ACME_EMAIL=your@email.com

   # Update service URLs
   VITE_API_BASE_URL=https://api.yourdomain.com
   VITE_GRAFANA_BASE_URL=https://grafana.yourdomain.com

   # Change ALL passwords
   JWT_SECRET_KEY=$(openssl rand -hex 32)
   POSTGRES_PASSWORD=$(openssl rand -base64 32)
   GRAFANA_ADMIN_PASSWORD=$(openssl rand -base64 16)
   ADMIN_PASSWORD=$(openssl rand -base64 16)

   # Production settings
   DEBUG=false
   HOT_RELOAD=false
   API_RELOAD=false
   API_WORKERS=4
   ```

3. **Deploy:**
   ```bash
   docker-compose -f docker-compose.prod.yml up -d
   ```

4. **Verify:**
   - Check Traefik dashboard: http://your-vps-ip:8080
   - Access services via HTTPS domains
   - Verify Let's Encrypt certificates

---

## Troubleshooting

### Development Issues

**Problem:** "Cannot connect to API at http://localhost:8000"
- **Check:** `docker-compose ps` — is API running?
- **Check:** `docker-compose logs api` — any errors?
- **Fix:** Restart with `docker-compose restart api`

**Problem:** "Grafana showing 404"
- **Check:** Accessing http://localhost:3000 (not grafana.localhost)
- **Fix:** Use direct port access, not domain

### Production Issues

**Problem:** "Traefik 404 error"
- **Check:** DNS records pointing to VPS
- **Check:** Traefik labels on services
- **Check:** `docker-compose -f docker-compose.prod.yml logs traefik`

**Problem:** "Let's Encrypt certificate failed"
- **Check:** Port 80 and 443 open in firewall
- **Check:** ACME_EMAIL set correctly
- **Check:** Domain resolves to VPS IP

---

## Files Reference

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Development configuration |
| `docker-compose.prod.yml` | Production configuration |
| `.env.example` | Template with all variables |
| `.env` | Your actual configuration (git-ignored) |
| `docs/DOCKER_ENV_GUIDE.md` | Detailed Docker & .env guide |
| `docs/WINDOWS_SETUP_NOTES.md` | Windows-specific dev notes |
| `docs/A4_traefik_topology.md` | Production network topology |

---

**Current Status:** Phase 2 complete
**Dev Environment:** ✅ Working (no Traefik, direct ports)
**Prod Environment:** ⏳ Not deployed yet (Phase 13)
