# Authelia OIDC — Implementation Tracker

> Living checklist for the Authelia OIDC auth/authz rollout. Canonical plan; mirrors the approved plan
> (`~/.claude/plans/let-s-plan-the-authelia-peaceful-donut.md`). Update statuses as work lands.
> Companion docs: `docs/Authentification.md` (how it works), `.agent/security-review.md` (findings).

> **STATUS 2026-06-14 — code-complete (A–I).** All sections implemented on branch
> `feature/authelia-implementation` and validated by `import api.main` + 32 passing API tests
> (`api/tests/test_oidc_auth.py`, incl. the route-coverage guard). Frontend validated by
> `vue-tsc --noEmit` (typecheck **passes clean** in a node:20 container). NOTE: `npm run lint` cannot
> run — the dashboard has **no eslint config** tracked anywhere in the repo, so eslint falls back to the
> default parser and throws `import/export reserved` / `Unexpected token <` on **every** `.ts`/`.vue`
> file (repo-wide, pre-existing, unrelated to this work). Adding an eslint config is a separate task.
> **Not yet deployed / E2E'd against a
> live Authelia.** Deviations from plan: (1) step-up grant is a stateless encrypted (Fernet) httpOnly
> cookie, single-use via clear-on-consume + the live single-instance lock (no DB migration); (2) prod
> JWT TTL=240 is documented in `.env.example` but not hard-enforced; (3) `VITE_AUTH_MODE` is baked at
> build (Dockerfile.prod + CI), not runtime. Open before live: verify `auth_time` refresh on
> `prompt=login` (authelia#2596); fill `authelia/` secrets on the VPS.

## Goal & constraints

Wire the **production** Authelia OIDC path. Three access tiers, derived from Authelia `groups`:

- **admins** → full actions (start runs, save config, activate weights, …).
- **viewers** → read-only dashboard + data, no mutating action.
- **no group** → authenticated but unauthorised → no session issued → redirect to `/no-access`
  (message only: "contact the site owner"; no contact details).

Hard constraints:
1. **Step-up re-auth** before launching a **live** run (on top of the `confirm_phrase = "I UNDERSTAND"`
   mainnet gate).
2. **Authelia requires a domain** → cannot run in dev. Dev keeps working with auth disabled via
   `DEV_USER_GROUP`; prod **must** force `AUTH_MODE=authelia_oidc`.

## Decisions (locked)

- **RP library = Authlib** (`authlib.integrations.starlette_client`). `oidcrp` is deprecated (merged into
  `idpy-oidc`); Authlib is maintained and FastAPI-idiomatic. (User decision.)
- **Pattern = BFF / Authorization Code + PKCE (S256).** API is a confidential RP; holds tokens
  server-side; issues the existing httpOnly session JWT. SPA never sees OIDC tokens.
- **No Traefik forward-auth** on api/dashboard routers — API-as-RP is the access control; forward-auth
  would block the OIDC callback. (Supersedes the ForwardAuth scheme in `docs/A5_auth_migration.md`.)
- **Authelia user backend = file** (`users_database.yml`, argon2), groups `admins`/`viewers`.
- **Step-up freshness window = 5 min**; **prod session TTL = 4h** (was 24h).
- Reuse existing seams: `Principal`, `require_admin`, `require_viewer`, CSRF double-submit, mainnet gate.

## Flow (reference)

```
SPA "Sign in" ──full-page nav──► API GET /auth/oidc/login
  → discovery (/.well-known/openid-configuration), gen state+nonce+PKCE, ENCRYPTED txn cookie, 302
  → Authelia /authorize (auth.trader.derveloy.eu) → user authenticates
  → API GET /auth/oidc/callback?code&state
      validate id_token (RS256 sig/iss/aud/nonce/exp), read groups → Role
        admin|viewer → issue session JWT (sub+role+email) → 302 return_to
        none         → no session, clear txn cookie → 302 /no-access
Later requests: session cookie + CSRF + require_admin/require_viewer (unchanged).
Live run step-up: max_age=0&prompt=login → fresh id_token → auth_time≤5min
  → RE-RESOLVE role from fresh groups → sub must match session → single-use grant bound to run_id.
```

## ⚠️ Risk to verify before relying on step-up

Authelia historically didn't always refresh `auth_time` on `prompt=login` (authelia#2596). **Verify**
against the deployed version that `max_age=0&prompt=login` yields a fresh `auth_time`. **Fallback:**
require `two_factor` policy for the `trader-api` client and/or gate live runs on session-age + a freshly
re-entered `confirm_phrase`, keeping the fresh-group re-resolution.

---

## Checklist

### A. Independent security fixes (ship first — no OIDC dependency)
- [ ] `api/config.py` `validate_production_secrets`: hard-fail boot if `environment=="prod"` and
      `auth_mode != "authelia_oidc"`. **(Critical #2)**
- [ ] `api/config.py`: reject wildcard CORS origins in prod. **(#14)**
- [ ] `api/auth/routes.py` `login`: return **404** when `auth_mode != "local"`. **(Critical #3)**
- [ ] `api/csrf_helper.py`: `hmac.compare_digest` instead of `!=`. **(#12)**

### B. OIDC module — `api/auth/oidc.py` (the "oidc utils class")
- [ ] Authlib OIDC client; **must not import `api/auth/jwt.py`** (RS256 vs HS256 separation). **(#4)**
- [ ] `build_authorize_redirect(request, *, prompt=None, max_age=None)` → discovery, PKCE S256, state,
      nonce; write **encrypted** txn cookie (dedicated `oidc_transaction_secret`). **(#5)**
- [ ] `validate_id_token(raw, expected_nonce)` → `algorithms=["RS256"]` hardcoded; validate
      `iss`/`aud`/`exp`/`iat`/`nbf`/`nonce`(const-time)/non-empty `sub`; JWKS from `jwks_uri`, 1h cache,
      single refresh on unknown `kid`, HTTPS, ≤5s timeout, **fail-closed**. **(#4)**
- [ ] `resolve_role(groups)`, `is_admin`, `is_viewer`, `has_access`; group names env-configurable.
- [ ] Dev bypass: synthesize groups from `DEV_USER_GROUP` **iff `environment=="dev"` AND
      `auth_mode=="local"`** (AND, never OR); prod synthesizer raises. **(#2)**
- [ ] `api/auth/dependencies.py`: replace the 501 `_resolve_oidc_principal` to decode session-JWT claims
      (`sub`/`role`/`email`); **never call Authelia per request**. **(#10)**

### C. OIDC routes
- [ ] `GET /auth/oidc/login` — no auth dep, rate-limited; validate+store `return_to` (allowlist
      `^/[A-Za-z0-9/_-]*$`, no `//`, no `..`, else `/`). **(#6, #9)**
- [ ] `GET /auth/oidc/callback` — no auth dep; validate id_token; issue session or 302 `/no-access`
      (hardcoded, no reason/group leak); always clear txn cookie. **(#13)**
- [ ] `GET /auth/oidc/stepup` — `require_admin`; save session `sub` in step-up txn cookie;
      `max_age=0&prompt=login`.
- [ ] `GET /auth/oidc/stepup/callback` — read session; validate fresh id_token, `auth_time` ≤300s
      (≤30s skew), **re-resolve admin from fresh groups**, **`sub` == session sub**; issue single-use
      grant bound to `run_id`. **(Critical #1)**
- [ ] `POST /auth/oidc/logout` — clear session; optional Authelia end-session redirect.
- [ ] Rate-limit all new endpoints.

### D. Live-run gate
- [ ] `api/routes/runs.py` / `api/models/run_control.py`: live runs require valid step-up grant **plus**
      admin + CSRF + `confirm_phrase`; missing/stale → 403 `step_up_required`.

### E. Config & secrets — `api/config.py` + `.env.example`
- [ ] Add `authelia_oidc_issuer` (prod: non-empty, `https://`), `authelia_oidc_client_id` (prod:
      non-empty), `authelia_oidc_client_secret` (prod ≥32, no weak patterns), `oidc_transaction_secret`
      (≥32), `oidc_admin_group`/`oidc_viewer_group` (`admins`/`viewers`), `dev_user_group`. **(#8)**
- [ ] Prod `jwt_access_token_expire_minutes` → 240; document revocation-lag. **(#11)**

### F. Cookie hygiene — `api/auth/routes.py`
- [ ] Session cookie host-only (`domain=None`); CSRF cookie `domain=".trader.derveloy.eu"`; both
      `SameSite=Strict` (fix the wrong "strict blocks cross-subdomain" comment); txn cookie host-only +
      `SameSite=Lax` + httpOnly + Secure. **(#7)**

### G. Frontend — `dashboard/src/`
- [ ] `router/index.ts`: public `/no-access` route + view; guard routes unauthorised → `/no-access`.
- [ ] Login: prod "Sign in" = `window.location.href = <API>/auth/oidc/login` (full nav, not fetch);
      keep local form in dev. **(#9)**
- [ ] `stores/auth.ts`: `isAdmin`/`isViewer` from `/auth/me`; viewers hide action buttons (extend
      existing gating on RunsView/RunCard/Optimizations).
- [ ] Live-run start: on `step_up_required` → redirect `/auth/oidc/stepup` → retry.

### H. Infrastructure — `docker-compose.prod.yml` + `authelia/`
- [ ] `authelia` service on `trader-network`; Traefik router `Host(auth.trader.derveloy.eu)` +
      websecure + Let's Encrypt; **no** forward-auth on api/dashboard.
- [ ] `authelia/configuration.yml` template (env-substituted secrets): OIDC provider; client
      `trader-api` (confidential, PKCE S256, redirect URIs to API callbacks, scopes
      `openid profile email groups`); `claims_policies` putting `groups` in id_token (req. v4.39+) via
      client `claims_policy`.
- [ ] `users_database.yml`: file backend, argon2, groups `admins`/`viewers`.
- [ ] `.gitignore`: add `authelia/` + `users_database.yml`; mount from absolute VPS path
      (`/etc/authelia/…:ro`), never repo-relative. **(#15)**
- [ ] Authelia secrets via env/`secrets:`. **(#8)**

### I. Documentation & tracking
- [x] `.agent/authelia-implementation.md` (this file).
- [x] `docs/Authentification.md` (how auth/authz works).
- [x] Update `.agent/security-review.md` todo list with findings #1–#17 from this design review.
- [x] Update `.agent/CONTINUITY.md` `[DECISIONS]` once implementation starts.
- [x] Route-coverage test: every non-allowlisted route has `require_admin`/`require_viewer`. **(#16)**

---

## Critical requirements (must all be true before live)

- [x] #1 step-up re-resolves role from fresh id_token + `sub` binding + single-use grant (cookie-scoped,
      not run_id-scoped — see status banner deviation #1).
- [x] #2 prod ⇒ `authelia_oidc` only (boot fail otherwise).
- [x] #3 `/auth/login` → 404 in OIDC mode.
- [x] #4 RS256-only id_token validation, full claim set, JWKS fail-closed, separate from `jwt.py`.
- [x] #5 encrypted single-use ≤5min txn cookie, dedicated secret.
- [x] #6 `return_to` relative-path allowlist (store + use).
- [x] #7 cookie domains narrowed, `SameSite=Strict`.
- [x] #8/#15 OIDC secrets validated in prod; `users_database.yml` gitignored + off-repo mount.
- [x] #12 constant-time CSRF compare.

## Verification (see plan for detail)

1. Dev: `AUTH_MODE=local`, `DEV_USER_GROUP=admins` → full; `viewers` → buttons hidden + 403 on mutate.
2. Boot guards: prod+local → exits non-zero; OIDC mode → `POST /auth/login` = 404.
3. OIDC happy path: admin authed, viewer read-only, no-group → `/no-access` (no cookie).
4. id_token hardening: forged HS256(pubkey) → 401; tampered state/nonce → reject; `return_to=evil` → `/`.
5. Step-up: demote admin→viewer mid-session → live step-up rejected (403); confirm `auth_time` refresh.
6. pytest (bot container) on new validators/guards; `eslint` on dashboard.
