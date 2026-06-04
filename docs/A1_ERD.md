# A1 — Entity Relationship Diagram (ERD)

## Vue d'ensemble

Ce document décrit le schéma complet de la base de données PostgreSQL + TimescaleDB du bot de trading.

## Principes de conception

1. **Immutabilité** : Rien n'est jamais supprimé (soft delete si nécessaire)
2. **Traçabilité** : Tout événement porte un `run_id`
3. **Snapshots** : Configuration capturée au démarrage de chaque run
4. **Time-series** : Utilisation des hypertables TimescaleDB pour les données temporelles

---

## Tables principales

### `runs`
Table centrale pour tous les types d'exécution (backtest, optimization, paper trading, live).

```sql
CREATE TABLE runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_type VARCHAR(20) NOT NULL, -- 'backtest', 'optimization', 'paper', 'live'
    status VARCHAR(20) NOT NULL, -- 'running', 'completed', 'failed', 'stopped'
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    config_snapshot JSONB NOT NULL, -- Snapshot complet de la configuration
    metadata JSONB, -- Métadonnées additionnelles
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_runs_type_status ON runs(run_type, status);
CREATE INDEX idx_runs_started_at ON runs(started_at DESC);
```

### `candles`
Hypertable TimescaleDB pour les données OHLCV.

```sql
CREATE TABLE candles (
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    open DECIMAL(20, 8) NOT NULL,
    high DECIMAL(20, 8) NOT NULL,
    low DECIMAL(20, 8) NOT NULL,
    close DECIMAL(20, 8) NOT NULL,
    volume DECIMAL(20, 8) NOT NULL,
    PRIMARY KEY (time, symbol, timeframe)
);

-- Convert to hypertable
SELECT create_hypertable('candles', 'time');

CREATE INDEX idx_candles_symbol_timeframe ON candles(symbol, timeframe, time DESC);
```

### `indicators_values`
Valeurs calculées des indicateurs techniques par run.

```sql
CREATE TABLE indicators_values (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES runs(id),
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    indicator_name VARCHAR(50) NOT NULL,
    values JSONB NOT NULL, -- Valeurs brutes de l'indicateur
    signal DECIMAL(5, 4) NOT NULL, -- Signal normalisé [-1, 1]
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_indicators_run_time ON indicators_values(run_id, time);
CREATE INDEX idx_indicators_symbol_name ON indicators_values(symbol, indicator_name, time DESC);
```

### `user_indicator`
Indicateur manuel configuré par l'utilisateur.

```sql
CREATE TABLE user_indicator (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(20) NOT NULL,
    signal DECIMAL(5, 4) NOT NULL, -- Valeur slider [-1, 1]
    note TEXT,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_user_indicator_symbol ON user_indicator(symbol);
CREATE INDEX idx_user_indicator_expires ON user_indicator(expires_at);
```

### `signals`
Décisions du bot avec score pondéré et snapshot des poids.

```sql
CREATE TABLE signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES runs(id),
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    signal_type VARCHAR(10) NOT NULL, -- 'entry_long', 'exit', 'skip'
    weighted_score DECIMAL(5, 4) NOT NULL, -- Score pondéré [-1, 1]
    weights_snapshot JSONB NOT NULL, -- Snapshot des poids actifs
    indicators_snapshot JSONB NOT NULL, -- Valeurs de tous les indicateurs
    decision_reason TEXT, -- Raison de la décision ou du skip
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_signals_run_time ON signals(run_id, time);
CREATE INDEX idx_signals_type ON signals(signal_type);
```

### `orders`
Ordres passés sur l'exchange.

```sql
CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES runs(id),
    signal_id UUID REFERENCES signals(id),
    exchange_order_id VARCHAR(100),
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL, -- 'buy', 'sell'
    order_type VARCHAR(20) NOT NULL, -- 'limit', 'market'
    status VARCHAR(20) NOT NULL, -- 'pending', 'filled', 'cancelled', 'rejected'
    quantity DECIMAL(20, 8) NOT NULL,
    price DECIMAL(20, 8),
    filled_quantity DECIMAL(20, 8) DEFAULT 0,
    filled_price DECIMAL(20, 8),
    commission DECIMAL(20, 8),
    placed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    filled_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_orders_run ON orders(run_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_exchange_id ON orders(exchange_order_id);
```

### `trades`
Trades complétés avec P&L.

```sql
CREATE TABLE trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES runs(id),
    symbol VARCHAR(20) NOT NULL,
    entry_order_id UUID REFERENCES orders(id),
    exit_order_id UUID REFERENCES orders(id),
    side VARCHAR(10) NOT NULL, -- 'long', 'short'
    entry_price DECIMAL(20, 8) NOT NULL,
    exit_price DECIMAL(20, 8) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    pnl DECIMAL(20, 8) NOT NULL, -- Profit & Loss en USDT
    pnl_percent DECIMAL(10, 4) NOT NULL, -- P&L en pourcentage
    commission_total DECIMAL(20, 8) NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL,
    closed_at TIMESTAMPTZ NOT NULL,
    duration_seconds INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_trades_run ON trades(run_id);
CREATE INDEX idx_trades_closed_at ON trades(closed_at DESC);
CREATE INDEX idx_trades_pnl ON trades(pnl DESC);
```

### `weights_sets`
Sets de poids optimisés (via Optuna ou manuels).

```sql
CREATE TABLE weights_sets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    source VARCHAR(20) NOT NULL, -- 'optuna', 'manual'
    weights JSONB NOT NULL, -- {"ema": 0.15, "macd": 0.20, ...}
    optimization_score DECIMAL(10, 4), -- Score Sharpe ou autre métrique
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_weights_active ON weights_sets(is_active);
```

### `optuna_studies`
Résultats des études d'optimisation Optuna.

```sql
CREATE TABLE optuna_studies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    study_name VARCHAR(100) NOT NULL,
    run_id UUID REFERENCES runs(id),
    n_trials INTEGER NOT NULL,
    best_value DECIMAL(10, 4),
    best_params JSONB,
    weights_set_id UUID REFERENCES weights_sets(id),
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_optuna_study_name ON optuna_studies(study_name);
```

### `users`
Utilisateurs (mono-user v1, prévu pour multi-users).

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);
```

### `notifications_log`
Historique des notifications Discord.

```sql
CREATE TABLE notifications_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    notification_type VARCHAR(50) NOT NULL,
    message TEXT NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status VARCHAR(20) NOT NULL, -- 'sent', 'failed'
    metadata JSONB
);

CREATE INDEX idx_notifications_sent_at ON notifications_log(sent_at DESC);
CREATE INDEX idx_notifications_type ON notifications_log(notification_type);
```

### `errors_log`
Erreurs et exceptions capturées.

```sql
CREATE TABLE errors_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID REFERENCES runs(id),
    error_type VARCHAR(100) NOT NULL,
    message TEXT NOT NULL,
    stack_trace TEXT,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB
);

CREATE INDEX idx_errors_run ON errors_log(run_id);
CREATE INDEX idx_errors_occurred_at ON errors_log(occurred_at DESC);
```

---

## Continuous Aggregates (TimescaleDB)

### Agrégat journalier du P&L

```sql
CREATE MATERIALIZED VIEW daily_pnl
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', closed_at) AS day,
    run_id,
    symbol,
    COUNT(*) AS trades_count,
    SUM(pnl) AS total_pnl,
    AVG(pnl) AS avg_pnl,
    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS winning_trades,
    SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) AS losing_trades
FROM trades
GROUP BY day, run_id, symbol;

-- Refresh policy
SELECT add_continuous_aggregate_policy('daily_pnl',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour');
```

---

## Diagramme ERD

*TODO: Générer un diagramme visuel avec dbdiagram.io ou équivalent*

---

## Notes de migration

- Phase 1 : Création du schéma initial
- Phase 7 : Activation des continuous aggregates
- Migration future Option B : Ajout de colonnes pour Grafana auth proxy
