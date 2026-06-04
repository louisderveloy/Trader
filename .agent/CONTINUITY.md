# CONTINUITY.md — Trader Bot Implementation

## [PLANS]

### 2026-06-03T18:45Z [USER] Project kickoff
Starting implementation of crypto trading bot per CLAUDE.md specification.

**Current phase:** Phase 3 — Indicators Engine ✅ Complete with full test coverage (77%)

**Phase 3 objectives:**
1. Create indicators module structure with common types and utilities
2. Implement 9 technical indicators (EMA, MACD, RSI, Stoch RSI, Bollinger, ATR, OBV, Fear & Greed, User)
3. Each indicator must expose: compute(candles, params) -> values and to_signal(values) -> float ∈ [-1, 1]
4. All signals must be normalized to [-1, 1] range
5. Use pure pandas/numpy implementation (no TA-Lib C dependency)
6. Add comprehensive unit tests (>70% coverage target)
7. Full type hints and docstrings per CLAUDE.md conventions
8. Structured JSON logging (no print() statements)

**Phase 0 objectives:**
1. Complete monorepo structure creation
2. Setup PostgreSQL + TimescaleDB + Redis infrastructure (docker-compose)
3. Setup Traefik with local HTTPS (mkcert)
4. Create .env.example with all variables documented
5. Setup Python tooling (ruff, pytest, dependencies)
6. Setup basic CI/CD (GitHub Actions for linting)
7. Initialize Alembic for DB migrations

**Next phases preview:**
- Phase 3: Indicators engine (8+ technical indicators)
- Phase 4: Strategy engine (weighted scoring)
- Phase 5: Backtesting engine (vectorbt + custom)

**Phase 2 objectives (completed):**
1. Create abstract ExchangeBase interface
2. Implement BinanceExchange connector with async support
3. Support testnet/mainnet environments
4. Implement all market data and order operations
5. Add comprehensive error handling with custom exceptions
6. Verify imports and code compilation

---

## [DECISIONS]

### 2026-06-03T18:45Z [CODE] Python version mismatch detected
- Dockerfile uses Python 3.14-slim, but CLAUDE.md specifies 3.13
- **Decision:** Will standardize on Python 3.13 as per spec

### 2026-06-03T18:45Z [CODE] Existing Bot/ structure
- Found minimal Bot/ directory with stub files for hot reload testing
- **Decision:** Will refactor to match proper monorepo structure (/bot, /api, /dashboard, etc.)

### 2026-06-03T20:00Z [USER] Exchange change from Bybit to Binance
- User is French resident and does not have access to Bybit
- **Decision:** Switch entire project from Bybit to Binance
- **Impact:** Updated CLAUDE.md, .env.example, docs/A2_config_params.md, requirements.txt, pyproject.toml
- **Changes:**
  - API credentials: `BYBIT_*` → `BINANCE_*`
  - SDK: `pybit` → `python-binance`
  - Commission fees: 0.075% (Bybit) → 0.1% (Binance spot taker)
  - Testnet: testnet.bybit.com → testnet.binance.vision
  - All documentation updated to reflect Binance

### 2026-06-03T22:00Z [CODE] Import path structure for bot/ directory
- **Issue:** Container working directory is `/app` (bot/ directory), not project root
- **Decision:** Use relative imports (`from exchanges.xxx`) instead of absolute (`from bot.exchanges.xxx`)
- **Impact:** Modified bot/exchanges/__init__.py and bot/exchanges/binance.py
- **Result:** Imports work correctly in container environment

### 2026-06-03T23:00Z [CODE] .env.example updated for dev/prod clarity
- **Issue:** .env.example still referenced Traefik and *.localhost domains for dev, inconsistent with current architecture
- **Decision:** Update .env.example to clearly distinguish dev vs prod configurations
- **Changes:**
  - Added header comment explaining dev (direct ports) vs prod (Traefik) architecture
  - Changed `VITE_API_BASE_URL` from `https://api.localhost` to `http://localhost:8000` for dev
  - Changed `VITE_GRAFANA_BASE_URL` from `https://grafana.localhost` to `http://localhost:3000` for dev
  - Marked Traefik section as "PRODUCTION ONLY" with clear note
  - Added commented production URL examples
  - Updated Grafana settings to reflect direct login in dev (not anonymous)
  - Added development service URLs reference section
- **Documentation:** Created docs/DEV_VS_PROD.md with complete architecture comparison
- **Result:** Clear separation between dev and prod configurations, no confusion about Traefik usage

### 2026-06-04T00:00Z [CODE] TA-Lib dependency approach for indicators
- **Issue:** requirements.txt includes ta-lib>=0.4.32, but Dockerfile doesn't install TA-Lib C library
- **Problem:** TA-Lib Python wrapper requires the C library to be compiled/installed first (complex build process)
- **Decision:** Use pure pandas/numpy implementations for all technical indicators
- **Rationale:**
  - Full control over calculations and normalization logic
  - No C dependency compilation issues in Docker
  - Easier to debug and maintain
  - Consistent with project requirement for structured logging and type hints
  - All indicators can be unit tested without external library constraints
- **Impact:** Remove ta-lib from requirements.txt, implement all indicators from scratch
- **Result:** Cleaner dependency tree, faster Docker builds, full transparency in calculations

### 2026-06-04T01:30Z [CODE] Testing infrastructure setup
- **Approach:** Run tests inside Docker container, not on host
- **Decision:** Mount ./tests directory to bot container, install dev dependencies only in dev mode
- **Implementation:**
  - Created requirements-dev.txt with pytest, pytest-asyncio, pytest-cov, pytest-mock
  - Updated Dockerfile with INSTALL_DEV build arg (true in dev, false in prod)
  - Updated docker-compose.yml to mount ./tests and set INSTALL_DEV=true
  - Created pytest.ini for configuration
  - Created run-tests.bat (Windows) and run-tests.sh (Linux/Mac) helper scripts
  - Created tests/README.md with comprehensive testing documentation
- **Result:** Clean separation of dev/prod dependencies, tests run in consistent containerized environment

### 2026-06-04T01:35Z [CODE] Bug discovered via unit tests: RSI Decimal/float type mismatch
- **Issue:** RSI divergence detection failed with "TypeError: unsupported operand type(s) for *: 'decimal.Decimal' and 'float'"
- **Location:** bot/indicators/rsi.py lines 115 and 120
- **Cause:** Multiplying Decimal values (from candle data) with Python floats (0.98, 1.02)
- **Fix:** Convert Decimal to float before comparison: `float(value) >= float(max_value) * 0.98`
- **Discovery:** Found by test_rsi.py test suite (7 failing tests)
- **Lesson:** Unit tests immediately caught type handling issues that would have caused runtime errors
- **Result:** All 34 indicator tests passing after fix

### 2026-06-04T01:50Z [CODE] Second Decimal/float bug discovered: OBV divergence detection
- **Issue:** Same Decimal/float type mismatch in OBV divergence detection
- **Location:** bot/indicators/obv.py lines 106 and 111
- **Discovery:** Found when running full test suite after adding test_obv.py
- **Fix:** Applied same conversion as RSI: convert Decimal to float before arithmetic
- **Pattern:** All divergence detection code that compares candle prices needs Decimal-to-float conversion
- **Lesson:** Similar code patterns have similar bugs; comprehensive testing catches them all
- **Result:** 98/98 tests passing (10 skipped)

---

## [PROGRESS]

### 2026-06-03T19:45Z [CODE] Phase 0 completed
All 7 tasks for Phase 0 infrastructure setup completed successfully:
- ✅ Task #1: Monorepo structure created (bot/, api/, dashboard/, grafana/, db/, docker/, docs/)
- ✅ Task #2: Complete docker-compose.yml with all services (PostgreSQL+TimescaleDB, Redis, Traefik, bot, api, dashboard, Grafana)
- ✅ Task #3: .env.example with comprehensive documentation (100+ parameters)
- ✅ Task #4: Python project setup (pyproject.toml, requirements.txt, Python 3.13)
- ✅ Task #5: Alembic initialized for database migrations
- ✅ Task #6: GitHub Actions CI workflow (lint, test, security scan, Docker build)
- ✅ Task #7: Documentation structure with 6 annexes (A1-A6)

### 2026-06-04T02:00Z [CODE] Phase 3 indicators implementation completed
All 9 technical indicators implemented successfully:
- ✅ Module structure: types.py, utils.py, __init__.py, README.md
- ✅ EMA: Exponential Moving Average with crossover detection
- ✅ MACD: Moving Average Convergence Divergence with histogram
- ✅ RSI: Relative Strength Index with divergence detection
- ✅ Stochastic RSI: Enhanced oscillator with %K and %D lines
- ✅ Bollinger Bands: Volatility bands with squeeze detection
- ✅ ATR: Average True Range for volatility measurement
- ✅ OBV: On Balance Volume with divergence detection
- ✅ Fear & Greed Index: External API integration with caching
- ✅ User Indicator: Database-backed manual user input

All indicators implement standard interface:
- `compute(candles, params) -> IndicatorResult`
- `to_signal(values) -> IndicatorSignal` (normalized to [-1, 1])

Features implemented:
- Pure pandas/numpy calculations (no TA-Lib dependency)
- Comprehensive type hints and docstrings
- Structured JSON logging (no print() statements)
- Signal normalization utilities in utils.py
- Extensive metadata for transparency and debugging

---

## [DISCOVERIES]

### 2026-06-03T19:35Z [TOOL] Bot/ directory case sensitivity
Windows filesystem allowed both Bot/ and bot/ during rename operation. Used mv Bot bot_new && mv bot_new bot to avoid case conflicts.

### 2026-06-03T20:25Z [TOOL] PostgreSQL bind mount incompatibility on Windows
**Issue:** PostgreSQL container unable to initialize with bind mount on Windows
**Error:** `initdb: error: could not change permissions of directory "/var/lib/postgresql/data": Operation not permitted`
**Cause:** Windows does not handle Linux permissions correctly for bind mounts. PostgreSQL runs as user `postgres` (UID 999) which cannot chmod Windows-created directories.
**Solution Applied:** Switched PostgreSQL to Docker named volume (`postgres_data`) instead of bind mount (`./volumes/postgres/`)
**Result:** PostgreSQL now healthy and operational with TimescaleDB 2.27.2
**Reference:** https://github.com/timescale/timescaledb-docker-ha/issues/460
**Note:** Other services (Redis, Grafana, logs) continue using bind mounts successfully

### 2026-06-03T21:30Z [TOOL] TimescaleDB continuous aggregates transaction limitation
**Issue:** Alembic migration failed with "CREATE MATERIALIZED VIEW ... WITH DATA cannot run inside a transaction block"
**Cause:** TimescaleDB continuous aggregates cannot be created inside transaction blocks, but Alembic runs all migrations in transactions by default
**Solution Applied:** Removed continuous aggregate (daily_pnl) from initial migration (001_initial_schema.py)
**Decision:** Defer continuous aggregates to Phase 7 as documented in A1_ERD.md
**Note:** Added comment in migration referencing future 002_continuous_aggregates.py migration

---

## [OUTCOMES]

### 2026-06-03T19:45Z [CODE] Phase 0 — Infrastructure Complete
**Status:** ✅ Complete

**Deliverables:**
1. **Monorepo structure**: Full directory hierarchy matching CLAUDE.md specification
2. **Docker infrastructure**: Complete docker-compose.yml with 6 services (PostgreSQL+TimescaleDB, Redis, bot, api, dashboard, Grafana)
3. **Configuration**: .env.example with 100+ documented parameters
4. **Python tooling**: pyproject.toml with ruff config, pytest setup, all dependencies listed
5. **Database migrations**: Alembic initialized and configured for async PostgreSQL
6. **CI/CD**: GitHub Actions workflow for Python linting, JS linting, tests, security scans, Docker builds
7. **Documentation**: 6 comprehensive annexes (ERD, config params, snapshot formats, network topology, auth migration, runbook)

**Note:** Traefik removed from dev environment per user request. Dev uses direct port access (3000, 5173, 8000). Traefik remains in docker-compose.prod.yml for production.

### 2026-06-03T21:35Z [CODE] Phase 1 — Database Schema Complete
**Status:** ✅ Complete

**Deliverables:**
1. **Initial migration**: db/migrations/versions/001_initial_schema.py with all 12 tables
2. **Tables created**: runs, candles, indicators_values, user_indicator, signals, orders, trades, weights_sets, optuna_studies, users, notifications_log, errors_log
3. **TimescaleDB hypertable**: candles table converted to hypertable for time-series optimization
4. **Indexes**: All performance indexes created as per ERD specification
5. **Foreign keys**: All referential integrity constraints established
6. **Alembic tracking**: alembic_version table tracking current schema version (001)
7. **Docker volume**: db/ directory mounted in bot container for migration execution

**Verification:**
- PostgreSQL 16.14 running with TimescaleDB 2.27.2
- All 12 tables + alembic_version confirmed via \dt
- candles confirmed as hypertable via timescaledb_information.hypertables
- Foreign key relationships verified on runs, trades, orders tables

**Deferred to Phase 7:**
- Continuous aggregate daily_pnl (requires transaction-free execution)

### 2026-06-03T22:30Z [CODE] Phase 2 — Binance Connector Complete
**Status:** ✅ Complete

**Deliverables:**
1. **Abstract base class**: exchanges/base.py with complete interface definition
2. **Binance implementation**: exchanges/binance.py with full async support
3. **Custom exceptions**: exchanges/exceptions.py with 9 specific error types
4. **Documentation**: exchanges/README.md with usage examples and API reference
5. **Test script**: test_binance_connector.py for manual verification
6. **Module exports**: Clean __init__.py exposing all public classes

**Implemented Methods:**
- Connection management: `connect()`, `disconnect()`
- Market data: `get_candles()`, `get_ticker()`
- Account: `get_balance()`
- Orders: `place_limit_order()`, `place_market_order()`, `cancel_order()`
- Order tracking: `get_order_status()`, `get_open_orders()`
- Utilities: `normalize_symbol()`, `normalize_timeframe()`

**Features:**
- Testnet/mainnet toggle via constructor
- AsyncClient from python-binance
- Decimal precision for all prices/quantities
- UTC datetime for all timestamps
- Comprehensive error handling (9 exception types)
- Proper logging with structured data
- 15 supported timeframes (1m to 1M)

**Error Handling:**
Custom exceptions for: Connection, Authentication, InsufficientBalance, InvalidSymbol, InvalidTimeframe, OrderNotFound, OrderReject, RateLimit, Generic Exchange errors

**Data Normalization:**
All responses normalized to standard format with Decimal and datetime types, ensuring consistency across potential future exchanges.

**Verification:**
- Code compiles: ✅ `from exchanges import BinanceExchange` works
- Imports tested in bot container: ✅ Passed

**Next steps:**
- Configure Binance testnet credentials in .env
- Run test_binance_connector.py to verify live connectivity
- Begin Phase 3: Indicators engine (EMA, MACD, RSI, Stoch RSI, Bollinger, ATR, OBV, Fear & Greed)

### 2026-06-04T02:30Z [CODE] Phase 3 — Indicators Engine Complete
**Status:** ✅ Complete

**Deliverables:**
1. **Module structure**: indicators/ directory with types.py, utils.py, __init__.py, README.md
2. **Core types**: CandleData, IndicatorResult, IndicatorSignal, IndicatorProtocol
3. **Utility functions**: Signal normalization helpers in utils.py
4. **9 Technical Indicators**:
   - **ema.py**: Fast/slow EMA crossover with golden/death cross detection
   - **macd.py**: MACD with signal line and histogram momentum analysis
   - **rsi.py**: RSI with overbought/oversold zones and divergence detection
   - **stoch_rsi.py**: Stochastic RSI with %K/%D crossovers and zone analysis
   - **bollinger.py**: Bollinger Bands with bandwidth and squeeze detection
   - **atr.py**: ATR volatility measurement with percentile ranking
   - **obv.py**: On Balance Volume with trend analysis and divergence
   - **fear_greed.py**: External API integration with 4-hour caching
   - **user_indicator.py**: Database-backed manual user input with expiration

**Standard Interface:**
All indicators implement:
- `compute(candles, params) -> IndicatorResult`: Calculate raw indicator values
- `to_signal(values) -> IndicatorSignal`: Normalize to [-1, 1] range

**Key Features:**
- Pure pandas/numpy implementation (no TA-Lib C dependency)
- All signals normalized to [-1, 1] range for strategy scoring
- Comprehensive metadata for debugging and transparency
- Type hints on all public functions
- Docstrings on all classes and public functions
- Structured JSON logging (no print() statements)
- Divergence detection (RSI, OBV)
- Crossover detection (EMA, MACD, Stoch RSI)
- Volatility analysis (Bollinger squeeze, ATR percentile)

**Normalization Utilities:**
- `normalize_to_range()`: Linear normalization
- `normalize_oscillator()`: RSI-style zone normalization (contrarian)
- `normalize_crossover()`: EMA-style crossover normalization
- `normalize_percentile()`: ATR-style percentile ranking
- `calculate_ema()`, `calculate_sma()`: Common calculations
- `safe_divide()`: Zero-safe division

**Configuration:**
All indicator parameters match A2_config_params.md specification:
- EMA: INDICATOR_EMA_FAST_PERIOD (50), INDICATOR_EMA_SLOW_PERIOD (200)
- MACD: INDICATOR_MACD_FAST (12), INDICATOR_MACD_SLOW (26), INDICATOR_MACD_SIGNAL (9)
- RSI: INDICATOR_RSI_PERIOD (14), INDICATOR_RSI_OVERBOUGHT (70), INDICATOR_RSI_OVERSOLD (30)
- Stoch RSI: INDICATOR_STOCH_RSI_PERIOD (14), K (3), D (3)
- Bollinger: INDICATOR_BOLLINGER_PERIOD (20), INDICATOR_BOLLINGER_STD (2.0)
- ATR: INDICATOR_ATR_PERIOD (14)
- OBV, Fear & Greed, User: No configuration parameters

**Dependencies:**
- Removed ta-lib from requirements.txt and pyproject.toml
- Updated pyproject.toml description from "Bybit" to "Binance"
- All calculations use pandas and numpy only

**Documentation:**
- Comprehensive README.md with usage examples and API reference
- Each indicator file includes detailed docstrings
- Signal interpretation and normalization logic documented

**Verification:**
- All 9 indicators created ✅
- Standard interface implemented ✅
- Signals normalized to [-1, 1] ✅
- No TA-Lib dependency ✅
- Type hints and docstrings ✅

**Testing:**
- Test infrastructure: Docker-based testing with dev dependencies separation
- Test fixtures: 5 fixtures providing 300 candles (uptrend, downtrend, sideways, volatile, insufficient)
- Test coverage: **98 tests** (10 skipped pending db.models)
- Results: ✅ **98/98 passing** (10 skipped)
- **Coverage achieved: 77%** ✅ (exceeds 70% target)
  - __init__.py: 100%
  - types.py: 100%
  - utils.py: 78%
  - ema.py: 76%
  - macd.py: 87%
  - rsi.py: 89%
  - stoch_rsi.py: 80%
  - bollinger.py: 83%
  - atr.py: 83%
  - obv.py: 86%
  - fear_greed.py: 70%
  - user_indicator.py: 15% (async tests skipped until db.models exists)
- Bugs found & fixed:
  - RSI: Decimal/float type mismatch in divergence detection
  - OBV: Same Decimal/float issue in divergence detection
- Test scripts: run-tests.bat (Windows), run-tests.sh (Linux/Mac)
- Configuration: pytest.ini with coverage reporting
- Coverage report: HTML report in htmlcov/

**Next steps:**
- Begin Phase 4: Strategy engine (weighted scoring)
