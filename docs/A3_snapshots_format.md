# A3 — Format des Snapshots JSON

## Vue d'ensemble

Ce document définit le format JSON des snapshots de configuration et de poids capturés lors du démarrage de chaque run et lors des décisions.

---

## Config Snapshot (runs.config_snapshot)

Capturé au démarrage de chaque run. Contient toute la configuration active.

```json
{
  "run_type": "live",
  "timestamp": "2024-12-31T15:30:00Z",
  "strategy": {
    "entry_threshold": 0.6,
    "exit_threshold": -0.3,
    "confirmation_candles": 2
  },
  "risk": {
    "max_trades_per_day": 5,
    "max_exposure_percent": 30.0,
    "position_size_mode": "confidence",
    "fixed_size_usdt": 100.0,
    "atr_multiplier": 2.0,
    "capital_risk_percent": 1.0
  },
  "stop_loss": {
    "mode": "atr",
    "atr_multiplier": 2.0,
    "fixed_percent": 2.0
  },
  "take_profit": {
    "mode": "atr",
    "atr_multiplier": 3.0,
    "fixed_percent": 4.0
  },
  "cooldown": {
    "after_trade_seconds": 3600
  },
  "exchange": {
    "name": "bybit",
    "testnet": true,
    "symbol": "BTCUSDT",
    "timeframe": "15m",
    "max_slippage_percent": 0.2,
    "order_timeout_seconds": 1800
  },
  "indicators": {
    "ema": {
      "fast_period": 50,
      "slow_period": 200
    },
    "macd": {
      "fast": 12,
      "slow": 26,
      "signal": 9
    },
    "rsi": {
      "period": 14,
      "overbought": 70.0,
      "oversold": 30.0
    },
    "stoch_rsi": {
      "period": 14,
      "k": 3,
      "d": 3
    },
    "bollinger": {
      "period": 20,
      "std": 2.0
    },
    "atr": {
      "period": 14
    }
  },
  "active_weights_set_id": "uuid-of-active-weights-set",
  "notifications": {
    "trade_opened": true,
    "trade_closed": true,
    "critical_error": true,
    "bot_stopped": true,
    "quota_reached": true,
    "optimization_complete": true
  }
}
```

---

## Weights Snapshot (signals.weights_snapshot)

Capturé à chaque décision. Contient les poids actifs des indicateurs.

```json
{
  "weights_set_id": "uuid-of-active-weights-set",
  "weights_set_name": "Optuna Study #42",
  "weights": {
    "ema": 0.15,
    "macd": 0.20,
    "rsi": 0.12,
    "stoch_rsi": 0.08,
    "bollinger": 0.10,
    "atr": 0.05,
    "obv": 0.15,
    "fear_greed": 0.10,
    "user_indicator": 0.05
  },
  "timestamp": "2024-12-31T15:35:00Z"
}
```

---

## Indicators Snapshot (signals.indicators_snapshot)

Capturé à chaque décision. Contient les valeurs brutes et signaux de tous les indicateurs.

```json
{
  "timestamp": "2024-12-31T15:35:00Z",
  "symbol": "BTCUSDT",
  "candle_close": 42350.50,
  "indicators": {
    "ema": {
      "ema_50": 42100.00,
      "ema_200": 41500.00,
      "signal": 0.45
    },
    "macd": {
      "macd_line": 125.30,
      "signal_line": 110.20,
      "histogram": 15.10,
      "signal": 0.65
    },
    "rsi": {
      "value": 58.5,
      "signal": 0.17
    },
    "stoch_rsi": {
      "k": 62.3,
      "d": 58.1,
      "signal": 0.24
    },
    "bollinger": {
      "upper": 43000.00,
      "middle": 42000.00,
      "lower": 41000.00,
      "signal": -0.15
    },
    "atr": {
      "value": 520.30,
      "signal": 0.0
    },
    "obv": {
      "value": 15234567890,
      "signal": 0.35
    },
    "fear_greed": {
      "value": 65,
      "classification": "Greed",
      "signal": 0.30
    },
    "user_indicator": {
      "value": 0.8,
      "note": "Bullish sentiment based on news",
      "expires_at": "2024-12-31T18:00:00Z",
      "signal": 0.8
    }
  }
}
```

---

## Backtest Result Snapshot (runs.metadata pour run_type='backtest')

Capturé à la fin d'un backtest. Contient les métriques de performance.

```json
{
  "backtest_engine": "vectorbt",
  "start_date": "2023-01-01",
  "end_date": "2024-12-31",
  "initial_capital": 10000.0,
  "final_capital": 12345.67,
  "total_return": 0.234567,
  "total_return_percent": 23.4567,
  "sharpe_ratio": 1.85,
  "sortino_ratio": 2.34,
  "max_drawdown": -0.15,
  "max_drawdown_percent": -15.0,
  "win_rate": 0.58,
  "profit_factor": 1.75,
  "total_trades": 120,
  "winning_trades": 70,
  "losing_trades": 50,
  "average_win": 125.30,
  "average_loss": -85.20,
  "largest_win": 450.00,
  "largest_loss": -320.00,
  "average_trade_duration_hours": 18.5,
  "exposure_time_percent": 42.3,
  "buy_and_hold_return": 0.18,
  "buy_and_hold_return_percent": 18.0,
  "alpha": 0.054567,
  "beta": 1.12
}
```

---

## Optimization Result Snapshot (optuna_studies.metadata)

Capturé à la fin d'une étude Optuna.

```json
{
  "study_name": "Walk-forward Study 2024-12-31",
  "n_trials": 100,
  "n_completed": 100,
  "n_pruned": 23,
  "optimization_time_seconds": 3625.5,
  "objective": "sharpe_ratio",
  "best_trial": {
    "number": 87,
    "value": 2.15,
    "params": {
      "weight_ema": 0.14,
      "weight_macd": 0.22,
      "weight_rsi": 0.11,
      "weight_stoch_rsi": 0.09,
      "weight_bollinger": 0.12,
      "weight_atr": 0.04,
      "weight_obv": 0.16,
      "weight_fear_greed": 0.08,
      "weight_user_indicator": 0.04
    },
    "user_attrs": {},
    "datetime_start": "2024-12-31T10:15:30Z",
    "datetime_complete": "2024-12-31T10:22:45Z"
  },
  "walk_forward": {
    "n_splits": 4,
    "train_ratio": 0.75,
    "split_results": [
      {
        "split": 1,
        "train_start": "2023-01-01",
        "train_end": "2023-09-30",
        "test_start": "2023-10-01",
        "test_end": "2023-12-31",
        "train_sharpe": 2.05,
        "test_sharpe": 1.92
      },
      {
        "split": 2,
        "train_start": "2023-04-01",
        "train_end": "2024-03-31",
        "test_start": "2024-04-01",
        "test_end": "2024-06-30",
        "train_sharpe": 2.12,
        "test_sharpe": 2.18
      }
    ]
  }
}
```

---

## Error Log Snapshot (errors_log.metadata)

Capturé lors d'une erreur.

```json
{
  "error_class": "OrderRejectedError",
  "error_code": "110001",
  "exchange_response": {
    "ret_code": 110001,
    "ret_msg": "Insufficient balance",
    "ext_code": "",
    "ext_info": "",
    "result": null
  },
  "order_details": {
    "symbol": "BTCUSDT",
    "side": "Buy",
    "order_type": "Limit",
    "qty": 0.005,
    "price": 42350.00
  },
  "context": {
    "run_id": "uuid-of-run",
    "signal_id": "uuid-of-signal",
    "available_balance": 45.30,
    "required_balance": 211.75
  }
}
```

---

## Notes d'implémentation

1. **Validation** : Tous les snapshots doivent être validés avec un schéma Pydantic avant insertion en DB
2. **Immutabilité** : Les snapshots ne sont jamais modifiés après insertion
3. **Compression** : Considérer la compression JSONB pour les gros snapshots (PostgreSQL le fait automatiquement)
4. **Recherche** : Utiliser les index GIN sur les colonnes JSONB pour la recherche rapide
5. **Versionning** : Ajouter un champ `snapshot_version` pour gérer l'évolution du format
