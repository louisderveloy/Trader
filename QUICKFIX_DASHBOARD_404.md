# QUICK FIX: Dashboard 404 Errors in Production

## Problem
Dashboard can't communicate with API in production. Logs show:
```
GET /api.trader.derveloy.eu/auth/me HTTP/1.1
```

This means the API URL is being treated as a **relative path** instead of an absolute URL.

## Root Cause
The GitHub Secret `VITE_API_BASE_URL` is configured **without the protocol** (e.g., `api.trader.derveloy.eu` instead of `https://api.trader.derveloy.eu`).

When axios receives a URL without `https://`, it treats it as a relative path, resulting in requests to `/api.trader.derveloy.eu/...` instead of `https://api.trader.derveloy.eu/...`.

## Immediate Fix (GitHub Secrets)

1. Go to your GitHub repository settings
2. Navigate to: **Settings → Secrets and variables → Actions**
3. Find the secret `VITE_API_BASE_URL`
4. Update it to: `https://api.trader.derveloy.eu` (or your actual API domain)
   - ✅ Correct: `https://api.trader.derveloy.eu`
   - ❌ Wrong: `api.trader.derveloy.eu`
   - ❌ Wrong: `http://api.trader.derveloy.eu` (use https in production)

5. Similarly, update `VITE_GRAFANA_BASE_URL` if configured:
   - ✅ Correct: `https://your-grafana-instance.com`
   - ❌ Wrong: `your-grafana-instance.com`

## Redeploy

After updating the secrets:

```bash
# Option 1: Push a new commit to main (triggers auto-deployment)
git commit --allow-empty -m "fix: trigger rebuild with correct API URL"
git push origin main

# Option 2: Manual workflow dispatch
# Go to Actions → Build and Deploy to VPS → Run workflow
```

## Code Changes (Already Applied)

The following files have been updated to fix the CSP issue:

1. **`dashboard/nginx.conf`**: Changed Content Security Policy from `https://*.yourdomain.com` to `https://*.derveloy.eu` to allow API requests

2. **`.env.example`**: Added warning comment about protocol requirement

## Verify After Deployment

Once redeployed, verify in browser console (F12):

```javascript
// Check that API_BASE_URL is correct
// In Network tab, requests should go to:
// https://api.trader.derveloy.eu/auth/me  ✅
// NOT: https://trader.derveloy.eu/api.trader.derveloy.eu/auth/me  ❌
```

## About the Other 404 Errors

Errors like these are **expected and harmless**:
```
GET /js/lkk_ch.js HTTP/1.1" 404
GET /js/twint_ch.js HTTP/1.1" 404
GET /assets/js/auth.js HTTP/1.1" 404
```

These are automated security scanners/bots testing for known vulnerabilities. Your nginx is correctly returning 404 for these non-existent files. This is **normal behavior** for any public web server.

### Optional: Reduce Scanner Noise in Logs

If you want to reduce log spam from scanners, you can add to `nginx.conf`:

```nginx
# Block common scanner paths (optional)
location ~ ^/(static/style/|js/lkk_ch|js/twint_ch|bot-connect\.js|vite\.svg) {
    access_log off;  # Don't log these scanner attempts
    return 404;
}
```

But this is **not required** - these errors don't affect functionality.

## Summary

**Critical Issue**: `VITE_API_BASE_URL` must include `https://` protocol
**Fix**: Update GitHub Secret to `https://api.trader.derveloy.eu`
**Redeploy**: Push to main or trigger workflow manually
**Scanner 404s**: Ignore them, they're harmless bots
