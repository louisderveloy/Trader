# A2 — Paramètres Configurables

## Vue d'ensemble

Liste exhaustive des paramètres configurables via le dashboard Vue.js. Chaque paramètre doit avoir un tooltip en français dans l'interface.

---

## Stratégie

| Paramètre | Type | Défaut | Tooltip FR |
|-----------|------|--------|------------|
| `STRATEGY_ENTRY_THRESHOLD` | float | 0.6 | Seuil de score pondéré pour entrer en position. Valeur entre -1 et 1. Plus le seuil est élevé, plus le bot sera sélectif. |
| `STRATEGY_EXIT_THRESHOLD` | float | -0.3 | Seuil de score pondéré pour sortir d'une position. Valeur entre -1 et 1. |
| `STRATEGY_CONFIRMATION_CANDLES` | int | 2 | Nombre de bougies de confirmation avant d'agir (anti-repainting). Augmenter pour réduire les faux signaux. |

---

## Gestion du Risque

| Paramètre | Type | Défaut | Tooltip FR |
|-----------|------|--------|------------|
| `RISK_MAX_TRADES_PER_DAY` | int | 5 | Nombre maximum de trades par jour. Protection contre le surtrading. |
| `RISK_MAX_EXPOSURE_PERCENT` | float | 30.0 | Pourcentage maximum du capital exposé simultanément. |
| `RISK_POSITION_SIZE_MODE` | enum | confidence | Mode de sizing : 'fixed' (% fixe du capital), 'confidence' (proportionnel au score), 'risk_atr' (basé sur ATR et % de capital à risquer). |
| `RISK_FIXED_SIZE_PERCENT` | float | 10.0 | Pourcentage du capital total par trade (mode 'fixed' uniquement). |
| `RISK_ATR_MULTIPLIER` | float | 2.0 | Multiplicateur ATR pour le calcul du sizing (mode 'risk_atr' uniquement). |
| `RISK_CAPITAL_RISK_PERCENT` | float | 1.0 | Pourcentage du capital à risquer par trade (mode 'risk_atr' uniquement). |

---

## Stop-Loss / Take-Profit

| Paramètre | Type | Défaut | Tooltip FR |
|-----------|------|--------|------------|
| `SL_MODE` | enum | atr | Mode stop-loss : 'atr' (basé sur ATR) ou 'fixed' (pourcentage fixe). |
| `SL_ATR_MULTIPLIER` | float | 2.0 | Multiplicateur ATR pour le stop-loss (mode 'atr' uniquement). Un stop-loss sera placé à prix_entrée - (ATR × multiplicateur). |
| `SL_FIXED_PERCENT` | float | 2.0 | Pourcentage de perte pour déclencher le stop-loss (mode 'fixed' uniquement). |
| `TP_MODE` | enum | atr | Mode take-profit : 'atr' (basé sur ATR) ou 'fixed' (pourcentage fixe). |
| `TP_ATR_MULTIPLIER` | float | 3.0 | Multiplicateur ATR pour le take-profit (mode 'atr' uniquement). Un take-profit sera placé à prix_entrée + (ATR × multiplicateur). |
| `TP_FIXED_PERCENT` | float | 4.0 | Pourcentage de gain pour déclencher le take-profit (mode 'fixed' uniquement). |

---

## Cooldown

| Paramètre | Type | Défaut | Tooltip FR |
|-----------|------|--------|------------|
| `COOLDOWN_AFTER_TRADE_SECONDS` | int | 3600 | Délai en secondes avant de pouvoir ouvrir une nouvelle position après la fermeture d'un trade. Protection contre les décisions émotionnelles. |

---

## Exchange (Binance)

| Paramètre | Type | Défaut | Tooltip FR |
|-----------|------|--------|------------|
| `BINANCE_DEFAULT_SYMBOL` | string | BTCUSDT | Paire de trading par défaut. |
| `BINANCE_DEFAULT_TIMEFRAME` | string | 15m | Timeframe principal des bougies (ex: 1m, 5m, 15m, 1h, 4h, 1d). |
| `BINANCE_MAX_SLIPPAGE_PERCENT` | float | 0.2 | Slippage maximum acceptable en pourcentage. Les ordres avec slippage supérieur seront annulés. |
| `BINANCE_ORDER_TIMEOUT_SECONDS` | int | 1800 | Timeout en secondes pour les ordres limite. Après ce délai, l'ordre limite non rempli sera annulé et remplacé par un ordre market (si nécessaire). |

---

## Indicateurs Techniques

### EMA (Exponential Moving Average)

| Paramètre | Type | Défaut | Tooltip FR |
|-----------|------|--------|------------|
| `INDICATOR_EMA_FAST_PERIOD` | int | 50 | Période de l'EMA rapide. Plus la période est courte, plus l'EMA réagit vite aux changements de prix. |
| `INDICATOR_EMA_SLOW_PERIOD` | int | 200 | Période de l'EMA lente. Utilisée pour identifier la tendance de fond. |

### MACD (Moving Average Convergence Divergence)

| Paramètre | Type | Défaut | Tooltip FR |
|-----------|------|--------|------------|
| `INDICATOR_MACD_FAST` | int | 12 | Période rapide du MACD. |
| `INDICATOR_MACD_SLOW` | int | 26 | Période lente du MACD. |
| `INDICATOR_MACD_SIGNAL` | int | 9 | Période de la ligne de signal MACD. |

### RSI (Relative Strength Index)

| Paramètre | Type | Défaut | Tooltip FR |
|-----------|------|--------|------------|
| `INDICATOR_RSI_PERIOD` | int | 14 | Période du RSI. Mesure la force du mouvement de prix. |
| `INDICATOR_RSI_OVERBOUGHT` | float | 70.0 | Seuil de surachat RSI. Au-dessus de ce niveau, l'actif est considéré suracheté. |
| `INDICATOR_RSI_OVERSOLD` | float | 30.0 | Seuil de survente RSI. En dessous de ce niveau, l'actif est considéré survendu. |

### Stochastic RSI

| Paramètre | Type | Défaut | Tooltip FR |
|-----------|------|--------|------------|
| `INDICATOR_STOCH_RSI_PERIOD` | int | 14 | Période du Stochastic RSI. Version oscillateur du RSI. |
| `INDICATOR_STOCH_RSI_K` | int | 3 | Période de lissage K du Stochastic RSI. |
| `INDICATOR_STOCH_RSI_D` | int | 3 | Période de lissage D du Stochastic RSI (signal). |

### Bollinger Bands

| Paramètre | Type | Défaut | Tooltip FR |
|-----------|------|--------|------------|
| `INDICATOR_BOLLINGER_PERIOD` | int | 20 | Période des Bollinger Bands. |
| `INDICATOR_BOLLINGER_STD` | float | 2.0 | Nombre d'écarts-types pour les bandes supérieure et inférieure. |

### ATR (Average True Range)

| Paramètre | Type | Défaut | Tooltip FR |
|-----------|------|--------|------------|
| `INDICATOR_ATR_PERIOD` | int | 14 | Période de l'ATR. Mesure la volatilité du marché. |

---

## Optimisation Optuna

| Paramètre | Type | Défaut | Tooltip FR |
|-----------|------|--------|------------|
| `OPTUNA_N_TRIALS` | int | 100 | Nombre d'essais pour l'étude d'optimisation. Plus élevé = meilleure exploration mais plus long. |
| `OPTUNA_SAMPLER` | enum | TPE | Algorithme d'échantillonnage : 'TPE' (Tree-structured Parzen Estimator, recommandé), 'Random', 'Grid'. |
| `OPTUNA_PRUNER` | enum | MedianPruner | Algorithme d'élagage : 'MedianPruner' (arrête les essais non prometteurs), 'HyperbandPruner'. |

---

## Backtesting

| Paramètre | Type | Défaut | Tooltip FR |
|-----------|------|--------|------------|
| `BACKTEST_INITIAL_CAPITAL` | float | 10000.0 | Capital initial en USDT pour le backtest. |
| `BACKTEST_COMMISSION_PERCENT` | float | 0.1 | Frais de commission par trade en pourcentage (0.1 = Binance spot taker fee). |

---

## Notifications Discord

| Paramètre | Type | Défaut | Tooltip FR |
|-----------|------|--------|------------|
| `NOTIFY_TRADE_OPENED` | bool | true | Envoyer une notification lorsqu'un trade est ouvert. |
| `NOTIFY_TRADE_CLOSED` | bool | true | Envoyer une notification lorsqu'un trade est fermé (avec P&L). |
| `NOTIFY_CRITICAL_ERROR` | bool | true | Envoyer une notification en cas d'erreur critique (connexion perdue, ordre rejeté). |
| `NOTIFY_BOT_STOPPED` | bool | true | Envoyer une notification lorsque le bot s'arrête. |
| `NOTIFY_QUOTA_REACHED` | bool | true | Envoyer une notification lorsqu'un quota est atteint (max trades/jour, exposition max). |
| `NOTIFY_OPTIMIZATION_COMPLETE` | bool | true | Envoyer une notification lorsqu'une étude d'optimisation Optuna est terminée. |
| `DISCORD_RATE_LIMIT_MESSAGES` | int | 10 | Nombre maximum de messages Discord par période. |
| `DISCORD_RATE_LIMIT_PERIOD_SECONDS` | int | 60 | Période en secondes pour le rate limiting Discord. |

---

## Poids des Indicateurs

Les poids sont gérés via la table `weights_sets` et activables depuis le dashboard. Ils ne sont pas des paramètres d'environnement.

| Indicateur | Plage | Tooltip FR |
|-----------|-------|------------|
| EMA | 0.0 - 1.0 | Poids du signal EMA dans le score pondéré. |
| MACD | 0.0 - 1.0 | Poids du signal MACD dans le score pondéré. |
| RSI | 0.0 - 1.0 | Poids du signal RSI dans le score pondéré. |
| Stochastic RSI | 0.0 - 1.0 | Poids du signal Stochastic RSI dans le score pondéré. |
| Bollinger | 0.0 - 1.0 | Poids du signal Bollinger Bands dans le score pondéré. |
| ATR | 0.0 - 1.0 | Poids du signal ATR dans le score pondéré. |
| OBV | 0.0 - 1.0 | Poids du signal OBV dans le score pondéré. |
| Fear & Greed | 0.0 - 1.0 | Poids du Fear & Greed Index dans le score pondéré. |
| User Indicator | 0.0 - 1.0 | Poids de l'indicateur manuel utilisateur dans le score pondéré. |

---

## Notes d'implémentation

- Tous les paramètres doivent être validés côté frontend ET backend
- Les tooltips doivent être affichés au survol dans le dashboard
- Utiliser le composant réutilisable `<ConfigField>` pour tous les paramètres
- Les changements de configuration doivent créer un nouveau snapshot (pas de modification de run en cours)
