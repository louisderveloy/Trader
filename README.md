# Trader

Bot de trading crypto automatisé pour Binance avec backtesting, optimisation et dashboard Vue.js.

## 🔒 Security

This project implements comprehensive security best practices:

### Implemented Security Features

- ✅ **Rate Limiting** - Protects all endpoints from brute force and DoS attacks
  - Login: 5 attempts/minute
  - Read endpoints: 60 requests/minute
  - Write endpoints: 30 requests/minute
  - Expensive operations (optimizations): 2 requests/hour

- ✅ **httpOnly Cookies** - JWT tokens stored in httpOnly cookies (XSS protection)
- ✅ **CSRF Protection** - Token-based protection on state-changing operations (planned - see Task 7)
- ✅ **Input Validation** - Comprehensive Pydantic validation with enums, length, and range checks (planned - see Task 8)
- ✅ **SQL Injection Protection** - Parameterized queries throughout (no raw SQL)
- ✅ **Security Headers** - CSP, HSTS, X-Frame-Options, X-Content-Type-Options
- ✅ **Network Hardening** - PostgreSQL restricted to localhost + firewall rules
- ✅ **Secret Validation** - Production secrets validated at startup (min 32 chars for JWT, 16 for DB)
- ✅ **Error Handling** - Generic error messages in production (no information disclosure)
- ✅ **CORS Restriction** - Explicit allowed methods and headers (no wildcards)

### Current Authentication Status

⚠️ **Testing Phase Only** - The current implementation uses basic username/password authentication. This is **acceptable for the testing phase** only.

**Production Deployment** will migrate to **Authelia** (external authentication provider) which provides:
- Proper password hashing (bcrypt/argon2)
- Multi-factor authentication (2FA)
- Advanced session management
- SSO capabilities

### Before Production Deployment

**CRITICAL**: Generate strong secrets before deploying to production:

```bash
# Generate JWT secret (32+ characters)
openssl rand -hex 32

# Generate database password (16+ characters)
openssl rand -base64 24
```

Update `.env` with these secrets. The application will **reject weak secrets** in production mode (`ENVIRONMENT=prod`).

### Firewall Configuration (Production)

Configure firewall to allow **only Grafana server IP** to access PostgreSQL:

```bash
# Replace <grafana-ip> with actual IP
sudo ufw allow from <grafana-ip> to any port 5432
sudo ufw deny 5432
sudo ufw enable
```

See `docs/A6_runbook.md` for detailed firewall setup.

### Security Documentation

- **Security Review Report**: `docs/security-report.md`
- **Operational Runbook**: `docs/A6_runbook.md` (includes security procedures)
- **Configuration Guide**: `docs/A2_config_params.md`

### Pre-Deployment Security Checklist

Before deploying to production, verify:

- [ ] All secrets generated with `openssl rand -hex 32` or `openssl rand -base64 24`
- [ ] `.env` file contains strong secrets (validated by startup check)
- [ ] PostgreSQL firewall configured (`sudo ufw status`)
- [ ] HTTPS enforced via Traefik
- [ ] Existing tests passing (`pytest tests/`)
- [ ] Security report reviewed (`docs/security-report.md`)
- [ ] Rate limiting enabled (`RATE_LIMIT_ENABLED=true`)
- [ ] CORS origins restricted to production domain only (no wildcards)
- [ ] `ENVIRONMENT=prod` in `.env`
- [ ] Authelia migration completed (future)

---

## 📦 Project Structure

See `CLAUDE.md` for complete project documentation.