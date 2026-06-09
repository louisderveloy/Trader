# QUICK FIX: CSRF 403 Forbidden in Production

## Problem
Dashboard can successfully log in, but all PATCH/POST/PUT/DELETE requests return **403 Forbidden**.

API logs show:
```
INFO: 172.18.0.2:60496 - "PATCH /config/strategy HTTP/1.1" 403 Forbidden
```

Browser console shows:
```javascript
API error: { status: 403, url: "/config/strategy", data: {...} }
```

## Root Cause
**SameSite cookie policy blocks cookies in cross-subdomain requests.**

Your architecture:
- **Dashboard**: `trader.derveloy.eu`
- **API**: `api.trader.derveloy.eu`

These are **different subdomains**, so browsers consider them **cross-site**.

The API was using `samesite="strict"` for cookies, which **blocks ALL cookies** in cross-site requests:
1. Dashboard fetches CSRF token from API → cookie `csrf_access_token` is set
2. Dashboard sends PATCH request with `X-CSRF-Token` header
3. **Browser blocks the `csrf_access_token` cookie** (SameSite=strict)
4. API validation fails: cookie missing → 403 Forbidden

## Solution Applied

Modified `api/auth/routes.py` to:
1. Change `samesite="strict"` → `samesite="lax"` (allows cross-subdomain)
2. Add `domain=".derveloy.eu"` in production (shares cookies across subdomains)

### Changes Made

**Line 72-79** (JWT cookie):
```python
response.set_cookie(
    key="access_token",
    value=access_token,
    httponly=True,
    secure=settings.environment == "prod",
    samesite="lax",  # Changed from "strict"
    domain=".derveloy.eu" if settings.environment == "prod" else None,  # Added
    max_age=settings.jwt_access_token_expire_minutes * 60,
)
```

**Line 139-146** (CSRF cookie):
```python
response.set_cookie(
    key="csrf_access_token",
    value=csrf_token,
    httponly=False,
    secure=settings.environment == "prod",
    samesite="lax",  # Changed from "strict"
    domain=".derveloy.eu" if settings.environment == "prod" else None,  # Added
    max_age=3600
)
```

**Line 105-109** (Logout cookie deletion):
```python
response.delete_cookie(
    key="access_token",
    domain=".derveloy.eu" if settings.environment == "prod" else None  # Added
)
```

## Required Actions

### 1. Verify Environment Variable (VPS .env file)

SSH to your VPS and check:
```bash
cd ~/trader  # Or your deploy path
cat .env | grep CORS_ORIGINS
```

Should be:
```bash
CORS_ORIGINS=https://trader.derveloy.eu
```

**NOT** `http://localhost:5173` (that's dev only)

If wrong, edit `.env`:
```bash
nano .env
# Change CORS_ORIGINS to: https://trader.derveloy.eu
# Save and exit (Ctrl+X, Y, Enter)
```

### 2. Redeploy API

Push the code changes to trigger deployment:
```bash
git add .
git commit -m "fix: allow cross-subdomain cookies for CSRF (SameSite=lax + domain)"
git push origin main
```

**OR** manually restart API on VPS:
```bash
cd ~/trader
docker compose -f docker-compose.prod.yml restart api
docker compose -f docker-compose.prod.yml logs api --tail=50
```

### 3. Test After Deployment

1. **Clear browser cookies** (important!):
   - F12 → Application → Cookies → `https://trader.derveloy.eu` → Delete all
   - F12 → Application → Cookies → `https://api.trader.derveloy.eu` → Delete all

2. **Refresh page** and login again

3. **Verify cookies are set correctly**:
   - F12 → Application → Cookies → `https://trader.derveloy.eu`
   - You should see `access_token` and `csrf_access_token`
   - **Check Domain column**: Should show `.derveloy.eu` (with leading dot)

4. **Test a configuration change**:
   - Dashboard → Configuration → Change a parameter
   - Should work without 403 error

5. **Verify in Network tab**:
   - F12 → Network → Find PATCH request
   - Headers tab → Request Headers:
     - `Cookie: access_token=...; csrf_access_token=...` ✅
     - `X-CSRF-Token: <token>` ✅

## Why This Happened

### SameSite Cookie Policies (simplified)

| SameSite Value | Cross-Site Behavior | Use Case |
|---|---|---|
| `strict` | **Blocks ALL** cross-site cookies | Same domain only (app.com → app.com) |
| `lax` | Allows safe cross-site (GET, but not POST/PATCH) | Most apps (allows navigation) |
| `none` | Allows ALL cross-site cookies (requires Secure) | Third-party embeds |

### Your Architecture Requires `lax` + `domain`

```
trader.derveloy.eu (Dashboard)
    ↓ PATCH request
api.trader.derveloy.eu (API)
```

This is **cross-site** (different subdomains), so:
- ❌ `SameSite=strict` blocks cookies → 403 errors
- ✅ `SameSite=lax` + `domain=.derveloy.eu` → cookies shared

## Security Implications

### Before (SameSite=strict)
- **More secure against CSRF** (but broken for your architecture)
- Cookies never sent cross-site

### After (SameSite=lax + domain=.derveloy.eu)
- **Still secure** for your use case
- Cookies shared across `*.derveloy.eu` subdomains
- CSRF protection via double-submit cookie pattern (still active)
- Cookies still `Secure=True` in production (HTTPS only)
- `access_token` still `httpOnly=True` (XSS protection)

### Defense-in-Depth Layers (all still active)
1. ✅ HTTPS only (`Secure=True`)
2. ✅ HttpOnly JWT cookie (XSS protection)
3. ✅ Double-submit CSRF token (validates header matches cookie)
4. ✅ SameSite=lax (prevents some CSRF attacks)
5. ✅ CORS configured (only allows `trader.derveloy.eu`)
6. ✅ Domain scoped to `.derveloy.eu` (not shared with other sites)

## Alternative Architectures (not recommended for you)

If you wanted to avoid cross-subdomain issues entirely:

### Option A: Same subdomain for both
- Dashboard: `trader.derveloy.eu`
- API: `trader.derveloy.eu/api` (reverse proxy)
- Pros: SameSite=strict works
- Cons: Requires Traefik path routing, more complex

### Option B: SameSite=none (not recommended)
- Allows truly cross-site cookies
- Requires `Secure=True`
- Less secure, not needed for your case

**Your current solution (lax + domain) is the right balance.**

## Troubleshooting

### Still getting 403 after fix?

1. **Clear ALL browser cookies** (old strict cookies might persist)
2. **Check API logs** for exact error:
   ```bash
   docker compose -f docker-compose.prod.yml logs api | grep -i csrf
   ```
3. **Verify cookie domain** in browser DevTools:
   - F12 → Application → Cookies
   - Domain should be `.derveloy.eu` (with dot)
4. **Check CORS_ORIGINS** in VPS `.env` file
5. **Restart API** to load new code:
   ```bash
   docker compose -f docker-compose.prod.yml restart api
   ```

### Cookies not being sent?

Check browser console for CORS errors:
- If you see `CORS policy: No 'Access-Control-Allow-Credentials'`
- API must have `allow_credentials=True` (already configured in `main.py:123`)

### Domain mismatch?

If your production domain is **not** `derveloy.eu`:
1. Edit `api/auth/routes.py`
2. Replace `.derveloy.eu` with your actual domain (e.g., `.yourdomain.com`)
3. Redeploy

## Summary

**Root Cause**: SameSite=strict blocks cookies between `trader.derveloy.eu` and `api.trader.derveloy.eu`

**Fix Applied**: SameSite=lax + domain=.derveloy.eu in `api/auth/routes.py`

**User Action Required**:
1. Verify CORS_ORIGINS in VPS .env
2. Redeploy (git push or docker compose restart api)
3. Clear browser cookies
4. Test configuration changes

**Security**: Still secure with defense-in-depth (HTTPS + httpOnly + CSRF validation + SameSite=lax)
