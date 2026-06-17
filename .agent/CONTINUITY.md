# CONTINUITY.md — Trader Bot Implementation

> Canonical briefing, designed to survive compaction. Condensed 2026-06-12 (was 2673 lines of
> per-phase deliverable dumps — see git history / module READMEs for the granular detail). Keep this
> file tight: record only non-derivable decisions, gotchas, and current state.

## Current state (2026-06-12)

- **Phases 0–9 complete** (infra, DB schema, Binance connector, indicators, strategy, backtesting,
  optimization, runs/logging, API, dashboard). Run-control plane (start/stop/kill/logs) shipped for
  backtest/paper/live **and** optimization runs, validated end-to-end.
- **Remaining roadmap:** Phase 11 Discord notifications (module built, integration/testing pending),
  Phase 12 automated tests (vitest/E2E), Phase 13 VPS prod deploy (CI/CD live), Phase 14 paper trading
  (4–8 wks), Phase 15 live. Phase 10 Grafana dropped (hosted externally).
- **Test suite:** ~411 passed / 10 skipped (instance-lock tests excluded from CI — need live PG).
- **Security:** full audit in `.agent/security-review.md` (23 findings, 2 critical). Address before
  any auth/deploy/secrets work.
- **Data caveat:** USDC-only rule; BTCUSDC candles fetched 2018-01-01→2026-06-01. BTCUSDT backtests
  fail with "No candles loaded".

---

## [DECISIONS]

### Architecture & stack
- **Messaging = PostgreSQL LISTEN/NOTIFY, no Redis** (Redis fully dropped). Bot never calls the API over
  HTTP. State written to DB; commands written to `run_commands` + NOTIFY; bot survives API/dashboard down.
- **Exchange = Binance** (switched from Bybit 2026-06-03: user is FR resident without Bybit access).
  SDK `python-binance`, taker fee 0.1%, testnet `testnet.binance.vision`.
- **Quote currency = USDC only** (USDT not authorised in EU); default symbol `BTCUSDC`.
- **Python 3.13** (Dockerfile was 3.14, standardised to spec).
- **Bot imports are relative** (`from exchanges.x`) — container WORKDIR is `/app` (the `bot/` dir), not
  repo root.
- **Indicators = pure pandas/numpy, no TA-Lib** (avoids C-lib compile in Docker; full control over
  normalization; all unit-testable). `user_indicator` fixed at 5% weight, not optimized.
- **Grafana hosted externally** (multi-project monitoring). Removed from both compose files; PG port
  5432 exposed for its connection; dashboard JSON kept in `/grafana/` for reference; dashboard may link
  out via `VITE_GRAFANA_BASE_URL`. CLAUDE.md rule: Vue.js = config+actions only, no complex graphs.
- **Tooling:** ruff removed project-wide (no Python linting; eslint stays). [[no-ruff-linting]]

### Run-control plane (2026-06-10 → 06-11, validated live)
- **RunSupervisor** (`bot/runs/supervisor.py`) lives in the bot container, replacing the old
  `while True: pass` entrypoint. Owns child processes, spawns `python -m main <type> ... --run-id <id>`
  via `create_subprocess_exec` (no shell). API and bot share only PostgreSQL (no Docker socket).
- **Transport:** `run_commands` table + `notify_run_command` trigger (migration 011, mirrors config
  trigger 008); supervisor LISTENs + 30s poll fallback; atomic claim via `processed_at`.
- **Run adoption:** API pre-creates a PENDING `runs` row + start command in one tx; bot adopts via
  `--run-id`, flipping PENDING→RUNNING instead of INSERTing. Graceful stop writes a terminal status.
- **Security model:** strict allowlist validation of every CLI-bound param in API (`StartRunRequest` /
  `StartOptimizationRequest`) **and** supervisor; **KILL is backtest+optimization only** (SIGKILL would
  orphan live/paper positions); mainnet gate = admin role + CSRF + required `confirm_phrase ==
  "I UNDERSTAND"` (`secrets.compare_digest`); Grafana read-only DB role (migration 012); logs served
  from per-run file on `bot_logs` mounted read-only into API, path-confined, with secret-redaction filter.
- **Auth:** role abstraction (`require_admin`/`require_viewer`, `AUTH_MODE=local|authelia_oidc`). `local`
  is the only working mode; Authelia OIDC is prod-only and **stubbed (501)** until rollout.
- **Optimization runs** reuse the whole plane unchanged. Single-instance = **PostgreSQL advisory lock**
  (key `'optimization': 1456372819`), NOT a migration; independent key ⇒ may run alongside paper/live.
  `optuna_studies` unchanged (completed-study store). `GET /optimizations` queries
  `runs LEFT JOIN optuna_studies` so running/failed studies are visible.

### Trading safety & correctness
- **Single-instance enforcement** via PG advisory locks (`bot/utils/instance_lock.py`): paper=1827364950,
  live=1923847563 (testnet+mainnet share the live lock). Crash-safe (released on connection close).
- **Hot config reload** via LISTEN/NOTIFY (migration 008 `notify_config_updated`): all running instances
  reload config+weights on any config INSERT/UPDATE, zero downtime, non-fatal if listener fails.
- **Position-close safeguards on stop** (`_ensure_all_positions_closed` in trading.py; `RunManager`
  guards; API `PATCH /runs/{id}/status` 400s if open trades): a run cannot close with open positions.
  Live mode also cancels open Binance orders.
- **Net P&L** (after entry+exit fees) stored in live/paper, matching backtesting. Capital updated with net.
- **Trades table tracks ongoing trades** (migration 007): row created `status='open'` on entry fill,
  updated `status='closed'` on exit fill. Orders table tracks individual buy/sell orders.
- **Order fills are verified, not assumed** (`self.pending_order` + `_check_pending_order`): live queries
  exchange `get_order_status` before marking filled; paper simulates 1-iteration delay + slippage. Earlier
  code dangerously marked limit orders filled on placement.

### Production / deploy
- **CI/CD** (`.github/workflows/docker-publish.yml`): parallel build of bot/api/dashboard → GHCR →
  SSH deploy to VPS on main. `docker-compose.prod.yml` uses GHCR images + `pull_policy: always`.
- **Auto-migrations on deploy:** `bot/entrypoint.sh` waits for PG (`pg_isready`), runs `alembic upgrade
  head` from `/db`, exits 1 (blocks bot start) on failure. `/db` SCP'd to VPS in the deploy job.
- **Cross-subdomain cookies:** JWT + CSRF cookies use `samesite="lax"` + `domain=".derveloy.eu"` in prod
  (dashboard `trader.derveloy.eu` ↔ API `api.trader.derveloy.eu` are cross-site under `strict`). CSRF =
  double-submit token. ⚠️ Security review Finding #5 recommends reverting to `strict` (same registrable
  domain ⇒ not actually blocked); revisit alongside that fix.
- **Prod PG binding** changed to `0.0.0.0:5432` for external Grafana (firewall-gated). ⚠️ Security review
  Finding #2 (CRITICAL) flags this — revert to `127.0.0.1` + SSH tunnel.

### Authentication — Authelia OIDC (2026-06-14, branch `feature/authelia-implementation`)
- **Pattern = BFF / Authorization Code + PKCE.** API is a confidential OIDC RP of **Authelia**
  (`auth.trader.derveloy.eu`); it holds OIDC tokens server-side and mints its own HS256 session cookie.
  SPA never sees OIDC tokens. **RP lib = Authlib** (user choice; `oidcrp` deprecated→`idpy-oidc`). Only
  `authlib.jose` is used (for RS256 id_token validation) — pinned `<2.0` (deprecated → migrate to
  `joserfc`). The flow is hand-rolled with httpx + an **encrypted (Fernet) transaction cookie** because
  Starlette session middleware only signs (would expose the PKCE verifier).
- **Roles from Authelia `groups`:** `admins`→ADMIN, `viewers`→VIEWER, none→`/no-access` (no session).
  Reuses existing `Principal`/`require_admin`/`require_viewer`/CSRF/mainnet gate unchanged — OIDC only
  changes *how the Principal is resolved at login* (`get_principal`: local-dev decodes session +
  `DEV_USER_GROUP`; oidc decodes our session JWT claims, never calls Authelia per request).
- **Step-up for live runs:** `POST /runs/start` (live) requires a fresh OIDC re-auth grant
  (`max_age=0&prompt=login`); the step-up callback **re-resolves admin from the fresh id_token groups**,
  binds fresh `sub` to session, checks `auth_time`≤5min, issues a single-use Fernet grant cookie.
  `_require_stepup_for_live` gates start; missing/stale → 403 `step_up_required` → SPA redirects.
- **No Traefik forward-auth** (would block the OIDC callback) — supersedes `docs/A5_auth_migration.md`.
- **Prod hard guards:** boot fails if `prod`+`AUTH_MODE=local`; `/auth/login`→404 in OIDC mode; OIDC
  secrets + non-wildcard CORS validated in prod. Cookies: session host-only, CSRF `.trader.derveloy.eu`,
  both `SameSite=Strict`; txn cookie Lax+encrypted. New: `api/auth/oidc.py`, `oidc_routes.py`,
  `cookies.py`; `authelia/` template (real `users_database.yml` lives at `/etc/authelia`, gitignored).
- **Status: code-complete A–I, validated by import + 32 API tests (`api/tests/`, new CI job).** NOT yet
  deployed/E2E against a live Authelia. Open: verify `auth_time` refresh on `prompt=login` (authelia#2596);
  bake `VITE_AUTH_MODE` in CI (done in Dockerfile.prod + workflow); enforce prod JWT TTL=240.
- **Docs:** `docs/Authentification.md` (how it works), `.agent/authelia-implementation.md` (tracker),
  `.agent/security-review.md` §Authelia (findings AO-1..AO-FOLLOWUP).

---

## [DISCOVERIES]

### Optimizer (load-bearing)
- **Walk-forward TEST score always 0.0 — weight-key namespace mismatch** (2026-06-11, fixed). Training
  used unprefixed normalized weights (real scores); but `study.best_params` is prefixed (`weight_<ind>`),
  un-normalized, missing the fixed weight — passed into test eval, every `weights.get('ema')` missed →
  ran on DEFAULTS → 0 trades → Sharpe 0.0. Same bug corrupted saved `weights_sets`. **Fix:** record exact
  weights via `trial.set_user_attr("weights", ...)`; runner uses `best_trial.user_attrs["weights"]` for
  test eval AND save; defensive warning in `vectorbt_engine.py` when no indicator key matches.
- **Quirk:** a 0-trade backtest scores Sharpe 0.0, which *beats* a losing config's negative Sharpe — with
  too few trials the optimizer can pick "do nothing." Explains all-zero low-trial runs.
- **Vectorbt Sharpe=0 root cause** (2026-06-04, fixed): `extract_trades()` used wrong column names
  (`Entry Idx`→`Entry Timestamp`, `Entry Price`→`Avg Entry Price`, etc.); misses returned `0` so all
  trades got identical timestamps/prices → constant equity → zero returns. Also: indicator `to_signal()`
  returns one value (last candle), so signals had to be **recomputed vectorized inline** in
  `vectorbt_engine.py` rather than calling indicator modules per-row.

### Dashboard / API (recent)
- **Optimisations filter/sort is server-side SQL** (2026-06-12, user rejected client-side). ORDER BY
  column from a whitelist map, direction from enum, all values bound as `$n` → no user input in SQL;
  symbol `pattern=^[A-Za-z0-9._-]+$`. Migration 015 adds partial indexes (`WHERE run_type='optimization'`).
  Facet `GET /optimizations/symbols` declared **before** `/{run_id}` so the literal path wins.
- **Weight-set activation from dashboard** (2026-06-12): `POST /optimizations/{run_id}/activate-weights`
  (admin+CSRF, deactivate-all + activate-one). `runs.weights_set_id` was never written by the runner →
  extended `link_optuna_study(..., weights_set_id)` + backfill migration 014. API reads
  `COALESCE(r.weights_set_id, s.weights_set_id)`. `runs.optuna_study_id` was `integer` but study id is
  `uuid` → migration 013 fixes the type (all rows were NULL).
- **`/weights` route** rewritten to real schema: UUID id, columns `id,name,weights,source,
  optimization_score,is_active,created_at`.

### Windows / Docker gotchas
- **PostgreSQL bind mount fails on Windows** (`could not change permissions`) → use named volume
  `postgres_data`, not `./volumes/...`. (TimescaleDB 2.27.2 / PG 16.)
- **Vite HMR serves stale .vue under Docker-on-Windows** even with polling → `docker compose restart
  dashboard` after edits if the served module looks old.
- **Bot/ vs bot/ case collision** during rename → `mv Bot bot_new && mv bot_new bot`.

### asyncpg / TimescaleDB
- DSN: strip `+asyncpg` from `DATABASE_URL` (asyncpg wants `postgresql://`).
- Candle time column is **`time`**, not `timestamp`. Dates must be tz-aware (UTC).
- Use **positional** params (`$1,$2`), not named. JSONB args need `json.dumps()` (asyncpg rejects dicts).
- Cast UUID columns to text (`id::text`) when returning to Pydantic/JSON.
- TimescaleDB continuous aggregates (`daily_pnl`) **can't be created in a transaction** → kept out of
  Alembic migrations (deferred).
- Decimal/float mismatch: convert Decimal→float before arithmetic in indicator divergence detection
  (hit in rsi.py and obv.py).
- Infinite/NaN scores can't go into PG NUMERIC or JSON → sanitize to None before insert.

---

## [OUTCOMES] — phase completion log

| Phase | Scope | Status |
|-------|-------|--------|
| 0 | Monorepo, docker-compose, .env.example, Alembic, CI | ✅ |
| 1 | DB schema — 12 tables, candles hypertable, FKs (migration 001) | ✅ |
| 2 | `ExchangeBase` + `BinanceExchange` (async, testnet/mainnet, 9 exc types) | ✅ |
| 3 | 9 indicators (pandas/numpy), `compute`/`to_signal`→[-1,1], 77% cov | ✅ |
| 4 | Strategy engine: weighted score, anti-repaint, 3 sizing modes, SL/TP, risk | ✅ |
| 5 | Backtesting: vectorbt + event-driven + coherence (<2% P&L) | ✅ |
| 6 | Optuna optimization + walk-forward (sliding/expanding) | ✅ |
| 7 | Runs management + structured logging (lifecycle, snapshots, errors) | ✅ |
| 8 | FastAPI backend (auth, runs, config, trades, orders, optimizations, signals) | ✅ |
| 9 | Vue 3 dashboard: real-data integration, analytics home, trades/orders, filters | ✅ |
| — | Bot CLI (`main.py`: fetch/backtest/optimize/paper/live) + historical fetch | ✅ |
| — | DB logging integration (orders, indicators, errors, notifications modules) | ✅ |
| — | CI/CD → GHCR + auto-migrations on VPS deploy | ✅ |
| 11 | Discord notifications | module built, integration pending |
| 12 | Automated tests (vitest/E2E) | pending |
| 13–15 | VPS prod / paper (4–8wk) / live | pending |
| Auth | Authelia OIDC (BFF, PKCE S256, step-up, dev bypass) — code-complete (A–I), 32 API tests + vue-tsc pass | ✅ code; not yet deployed/E2E |

> **Auth note (2026-06-14):** Authelia OIDC implemented on `feature/authelia-implementation`. Validated:
> `import api.main` OK, 32 `api/tests/test_oidc_auth.py` pass (incl. route-coverage guard), frontend
> `vue-tsc --noEmit` clean. `npm run lint` is non-functional repo-wide (no eslint config tracked → default
> parser fails on all `.ts`/`.vue`); pre-existing, out of scope. Pre-deploy TODO: fill `authelia/` secrets
> on VPS; verify `prompt=login`/`max_age=0` refreshes `auth_time` (authelia#2596); enforce prod JWT TTL=240;
> migrate `authlib.jose`→`joserfc`. Tracker: `.agent/authelia-implementation.md`.

**Objective:** beat buy-and-hold BTC over 1 year live; formal eval 12 months after Phase 15.

---

## [PROGRESS] Issue #17 — real stop-loss (branch `feature/stop-loss`, started 2026-06-17)

**Problem found:** SL/TP calc layer (`strategy/stops.py`) was complete + tested but NO execution path
used it. Live/paper/testnet hardcoded 2%/4% (`scripts/trading.py`) and never called the engine;
`event_driven.py`'s `get_strategy_decision` is a SKIP stub; `vectorbt_engine.py` had no SL/TP; `trades`
table lacked SL/TP/exit_reason columns. (This explains the -8% Louis saw in paper: hardcoded 2% checked
only on the latest *close* every ~60s — discrete sampling overshoots/misses; 60s cadence ruled out of
scope by user.) Latent bug: engine read ATR under `values["value"]` but indicator emits `values["atr"]`.

**User decisions:** native Binance OCO/STOP **+** software fallback (manage stop-order state +
cancellation on exit); refactor loop → StrategyEngine; single PR segmented by commits.

**Done (committed):**
- C1: `indicators.compute_all_indicators()` — shared helper, attaches `.signal` to IndicatorResult.
  fear_greed/user_indicator are neutral placeholders (async/DB, can't run in sync loop).
- C2: migration `016` adds `stop_loss_price`/`take_profit_price`/`exit_reason` to `trades`; trading.py
  persists them. Single alembic head = 016 (chain 003→7f964c375235→005→…→016).
- C3: `_trading_iteration` now delegates to `engine.make_decision`; removed duplicate
  `_calculate_signals`/`_calculate_weighted_score`/`_log_score`/confirmation gating. Entries use
  `decision.stop_loss_price/take_profit_price/position_size_qty`. Fixed ATR key bug. SL/TP price
  monitoring kept as `_price_stop_reason` (precedence over signal exit). Verified by
  `tests/test_trading_stop_loss.py` (real loop: ATR stop not 2%; price breach → "stop_loss" exit).

**⚠ Behavioural shift to flag:** paper now sizes via engine `position_size_mode` (default CONFIDENCE,
not 95%-all-in) and scores on the weight-normalized scale (`Σ|w|`), so entry/exit frequency + sizes
differ from before. Same thresholds (0.6/-0.3).

**Done (committed) cont'd:**
- C4: native Binance OCO (`place_oco_sell_order`/`cancel_oco_order` in base+binance, verified via
  Context7). trading.py: OCO placed on live entry fill; `_reconcile_native_stop` detects server-side
  fills + closes without a new order; `_cancel_native_stop` before signal market-exit (anti
  double-sell); paper=software-only. Tests `tests/test_native_stop.py` (mocked). **Live OCO
  fill-reconciliation still needs a testnet E2E before live (pre-Phase-14).** Full suite 423 pass/10 skip.

**DISCOVERY:** event-driven backtester (`event_driven.py`) is **non-functional scaffold** — broken engine
init (no run_id, flat kwargs) + `get_strategy_decision` SKIP stub with wrong TradingDecision kwargs.
`test_backtesting_coherence.py` only tests compare logic, never runs a backtester.

**User decision (2026-06-17):** vectorbt SL/TP now; **event-driven completion deferred to follow-up issue #26.**

**Done (committed) cont'd:**
- C6: vectorbt `from_signals` now passes `sl_stop`/`tp_stop` as fractions (FIXED=pct/100; ATR=per-bar
  `atr*mult/close`, warm-up→no stop). Raw ATR retained on signals_df. Tests `tests/test_vectorbt_stops.py`
  (incl. real from_signals applying sl_stop). Verified via Context7.
- C7: tests delivered per-commit (test_trading_stop_loss, test_native_stop, test_vectorbt_stops + engine
  fixture fix). Coherence end-to-end test deferred with event-driven (#26).

**CRITICAL FIX (real-DB verification):** `engine.load_active_weights` assumed `row["weights"]` was a
dict, but asyncpg returns JSONB as **str** (bot pool has no codec). Once the loop started calling
`make_decision`, `calculate_weighted_score` did `str.items()` → raised → swallowed by the loop guard as
"decision skipped" **every iteration → bot silently never trades**. Fixed with defensive `json.loads`;
regression test simulates str-JSONB. Found by seeding runs/config/weights_sets and executing all three
write paths (`make_decision`→`_log_score`/`_log_decision`, `_create_trade_entry`, `_log_trade`) against
the live migrated DB — all clean, returned `entry_long` with ATR SL/TP, rows persisted, cleaned up.

**ISSUE #17 STATUS: COMPLETE for this PR** (branch `feature/stop-loss`, 8 commits + docs). Full suite
**428 pass / 10 skip**. Follow-up **#26** tracks event-driven backtester completion. PR pending user
(never open PR to main — open to Dev/equivalent; only user merges).

**Pre-live TODO (not blocking PR):** testnet E2E of the native OCO fill-reconciliation path before
Phase 15. Backtest runner should populate `strategy_params['stop_loss'/'take_profit']` so vectorbt reads
real config (currently defaults) — folded into #26.

**Test env:** run in bot container. Bash path-mangles `/app`; prefix `MSYS_NO_PATHCONV=1` and use
`docker compose run --rm --entrypoint python bot -m pytest /tests/...`. pytest addopts forces `--cov=bot`.
