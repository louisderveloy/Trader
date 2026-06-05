# Trading Bot - Guide d'utilisation

Bot de trading crypto automatisé pour Binance. Ce guide explique comment utiliser toutes les fonctionnalités du bot.

## Table des matières

1. [Prérequis](#prérequis)
2. [Démarrage rapide](#démarrage-rapide)
3. [Commandes disponibles](#commandes-disponibles)
4. [Workflow recommandé](#workflow-recommandé)
5. [Configuration](#configuration)
6. [Résolution de problèmes](#résolution-de-problèmes)

---

## Prérequis

### 1. Démarrer l'infrastructure Docker

```bash
# Depuis la racine du projet
docker compose up -d
```

Cela démarre :
- PostgreSQL + TimescaleDB (base de données)
- Redis (messaging)
- Bot container (prêt à exécuter les commandes)
- API FastAPI
- Dashboard Vue.js

### 2. Configurer les credentials Binance

Créer un fichier `.env` à la racine du projet (copier `.env.example`) :

```bash
# API Binance Testnet (pour tests sans risque)
BINANCE_TESTNET_API_KEY=your_testnet_api_key
BINANCE_TESTNET_API_SECRET=your_testnet_api_secret

# API Binance Mainnet (pour trading réel - ATTENTION!)
BINANCE_MAINNET_API_KEY=your_mainnet_api_key
BINANCE_MAINNET_API_SECRET=your_mainnet_api_secret
```

**Obtenir les clés testnet :** https://testnet.binance.vision/

### 3. Vérifier que tout fonctionne

```bash
# Vérifier les containers
docker compose ps

# Vérifier tous les services (PostgreSQL, Redis, variables d'environnement)
docker compose exec bot python -m main status
```

Si tous les services sont marqués `[✓] HEALTHY`, vous êtes prêt à utiliser le bot.

---

## Démarrage rapide

Toutes les commandes s'exécutent via Docker :

```bash
docker compose exec bot python -m main <commande> [options]
```

### Exemple complet (5 minutes)

```bash
# 1. Récupérer des données historiques (2 ans)
docker compose exec bot python -m main fetch \
  --symbol BTCUSDT --timeframe 15m \
  --start-date 2024-01-01 --end-date 2025-12-31

# 2. Lancer une optimisation (trouvera les meilleurs poids)
docker compose exec bot python -m main optimize run \
  --study-name btc_2024 --n-trials 50 --n-splits 3

# 3. Backtest pour valider la stratégie
docker compose exec bot python -m main backtest \
  --symbol BTCUSDT --start-date 2024-06-01 --end-date 2024-12-31

# 4. Paper trading (simulation temps réel)
docker compose exec bot python -m main paper --symbol BTCUSDT
```

---

## Commandes disponibles

### `fetch` - Récupérer des données historiques

Télécharge les bougies OHLCV depuis Binance et les stocke en base de données.

```bash
docker compose exec bot python -m main fetch \
  --symbol BTCUSDT \
  --timeframe 15m \
  --start-date 2024-01-01 \
  --end-date 2024-12-31
```

| Option | Description | Défaut |
|--------|-------------|--------|
| `--symbol` | Paire de trading | **Requis** |
| `--timeframe` | Intervalle des bougies | `15m` |
| `--start-date` | Date de début (YYYY-MM-DD) | **Requis** |
| `--end-date` | Date de fin (YYYY-MM-DD) | **Requis** |
| `--testnet` | Utiliser le testnet Binance | `false` |

**Notes :**
- Le mainnet a des années de données historiques
- Le testnet n'a que quelques semaines de données
- La commande est idempotente (peut être relancée sans duplicata)

---

### `backtest` - Exécuter un backtest

Teste la stratégie sur des données historiques.

```bash
docker compose exec bot python -m main backtest \
  --symbol BTCUSDT \
  --start-date 2024-01-01 \
  --end-date 2024-06-01 \
  --initial-capital 10000
```

| Option | Description | Défaut |
|--------|-------------|--------|
| `--symbol` | Paire de trading | `BTCUSDT` |
| `--timeframe` | Intervalle des bougies | `15m` |
| `--start-date` | Date de début | **Requis** |
| `--end-date` | Date de fin | **Requis** |
| `--initial-capital` | Capital initial en USDT | `10000` |
| `--weights-set-id` | UUID du set de poids à utiliser | Set actif |
| `--engine` | Moteur (`vectorbt` ou `event_driven`) | `vectorbt` |
| `--save` | Sauvegarder les résultats en base | `false` |

**Sortie :**
```
================================================================================
BACKTEST RESULTS
================================================================================

========================================
PERFORMANCE SUMMARY
========================================
Total Return:          15.42%
Total P&L:           1542.00 USDT
Final Capital:      11542.00 USDT
Buy & Hold Return:     8.50%
Excess Return:         6.92%

========================================
TRADE STATISTICS
========================================
Total Trades:            127
Winning Trades:           73
Losing Trades:            54
Win Rate:             57.48%
Profit Factor:          1.85

========================================
RISK METRICS
========================================
Sharpe Ratio:           1.45
Sortino Ratio:          2.12
Max Drawdown:          -8.50%
```

---

### `optimize` - Optimisation des poids

Utilise Optuna pour trouver les meilleurs poids d'indicateurs via walk-forward analysis.

#### Lancer une optimisation

```bash
docker compose exec bot python -m main optimize run \
  --study-name btc_optimization_2024 \
  --symbol BTCUSDT \
  --n-trials 100 \
  --n-splits 4 \
  --objective sharpe_ratio
```

| Option | Description | Défaut |
|--------|-------------|--------|
| `--study-name` | Nom de l'étude | **Requis** |
| `--symbol` | Paire de trading | `BTCUSDT` |
| `--timeframe` | Intervalle des bougies | `15m` |
| `--start-date` | Date de début | Toutes les données |
| `--end-date` | Date de fin | Toutes les données |
| `--n-trials` | Nombre d'essais par split | `100` |
| `--n-splits` | Nombre de splits walk-forward | `4` |
| `--objective` | Métrique à optimiser | `sharpe_ratio` |

**Objectifs disponibles :**
- `sharpe_ratio` (recommandé) - Ratio rendement/risque
- `sortino_ratio` - Comme Sharpe mais pénalise seulement la volatilité négative
- `profit_factor` - Gains totaux / Pertes totales
- `win_rate` - Pourcentage de trades gagnants
- `total_return` - Rendement total

#### Voir les études existantes

```bash
docker compose exec bot python -m main optimize list
```

Cette commande affiche la liste des études avec leur **Optimization ID** (UUID unique).

#### Voir les meilleurs résultats d'une étude

```bash
# Utilisez l'Optimization ID obtenu via la commande 'list'
docker compose exec bot python -m main optimize best --optimization-id <UUID>

# Exemple :
docker compose exec bot python -m main optimize best --optimization-id 102e4887-5059-45ce-a536-d8c86eda74a3
```

**Note :** Utilisez l'**Optimization ID** (affiché par `optimize list`) et non le nom de l'étude, car les noms ne sont pas uniques.

#### Lister les sets de poids

```bash
docker compose exec bot python -m main optimize weights --show-weights
```

#### Activer un set de poids

```bash
docker compose exec bot python -m main optimize activate --weights-set-id <UUID>
```

---

### `paper` - Paper Trading (simulation)

Lance le bot en mode simulation. Aucun ordre réel n'est passé.

```bash
docker compose exec bot python -m main paper \
  --symbol BTCUSDT \
  --timeframe 15m
```

| Option | Description | Défaut |
|--------|-------------|--------|
| `--symbol` | Paire de trading | `BTCUSDT` |
| `--timeframe` | Intervalle des bougies | `15m` |

**Comportement :**
- Utilise les prix réels du testnet
- Simule les ordres (pas d'exécution réelle)
- Enregistre tout en base de données
- Publie les événements sur Redis
- Capital initial : 10,000 USDT

**Pour arrêter :** `Ctrl+C` (arrêt gracieux)

---

### `live` - Trading en direct

Lance le bot en trading réel. **ATTENTION : utilise de l'argent réel !**

#### Sur testnet (recommandé pour commencer)

```bash
docker compose exec bot python -m main live \
  --symbol BTCUSDT \
  --testnet
```

#### Sur mainnet (argent réel)

```bash
docker compose exec bot python -m main live \
  --symbol BTCUSDT
```

Une confirmation est demandée pour le mainnet. Tapez `YES I UNDERSTAND` pour continuer.

| Option | Description | Défaut |
|--------|-------------|--------|
| `--symbol` | Paire de trading | `BTCUSDT` |
| `--timeframe` | Intervalle des bougies | `15m` |
| `--testnet` | Utiliser le testnet | `false` |
| `--confirm` | Sauter la confirmation mainnet | `false` |

---

### `status` - Vérifier l'état du système

Vérifie la connexion aux services (PostgreSQL, Redis) et les variables d'environnement.

```bash
docker compose exec bot python -m main status
```

**Sortie :**
```
================================================================================
TRADING BOT - SYSTEM STATUS
================================================================================
Timestamp: 2024-01-15T10:30:00+00:00
Environment: dev
================================================================================

ENVIRONMENT: [✓] HEALTHY
  Message: All required variables present

DATABASE: [✓] HEALTHY
  Message: Connected

REDIS: [✓] HEALTHY
  Message: Connected

================================================================================
STATUS: All services are healthy ✓
================================================================================
```

**Notes :**
- Utile pour vérifier que tout est prêt avant de lancer un backtest ou une optimisation
- Retourne un code de sortie 0 si tout est OK, 1 sinon
- Le container bot utilise automatiquement cette commande au démarrage

---

## Workflow recommandé

### Phase 1 : Préparation des données

```bash
# Récupérer 2 ans de données historiques
docker compose exec bot python -m main fetch \
  --symbol BTCUSDT --timeframe 15m \
  --start-date 2023-01-01 --end-date 2025-01-01
```

### Phase 2 : Optimisation

```bash
# Optimiser les poids d'indicateurs
docker compose exec bot python -m main optimize run \
  --study-name btc_v1 \
  --n-trials 200 \
  --n-splits 5 \
  --objective sharpe_ratio

# Vérifier les résultats
docker compose exec bot python -m main optimize best --study-name btc_v1
```

### Phase 3 : Validation par backtest

```bash
# Tester sur une période non utilisée pour l'optimisation
docker compose exec bot python -m main backtest \
  --symbol BTCUSDT \
  --start-date 2024-07-01 \
  --end-date 2024-12-31
```

### Phase 4 : Paper trading (4-8 semaines minimum)

```bash
# Tester en conditions réelles sans risque
docker compose exec bot python -m main paper --symbol BTCUSDT
```

### Phase 5 : Live trading testnet

```bash
# Tester sur le testnet Binance
docker compose exec bot python -m main live --symbol BTCUSDT --testnet
```

### Phase 6 : Live trading mainnet (avec prudence)

```bash
# Commencer avec un petit capital !
docker compose exec bot python -m main live --symbol BTCUSDT
```

---

## Configuration

### Variables d'environnement principales

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | URL de connexion PostgreSQL |
| `REDIS_URL` | URL de connexion Redis |
| `BINANCE_TESTNET_API_KEY` | Clé API Binance testnet |
| `BINANCE_TESTNET_API_SECRET` | Secret API Binance testnet |
| `BINANCE_MAINNET_API_KEY` | Clé API Binance mainnet |
| `BINANCE_MAINNET_API_SECRET` | Secret API Binance mainnet |

### Paramètres de stratégie (configurables via dashboard)

| Paramètre | Description | Défaut |
|-----------|-------------|--------|
| `entry_threshold` | Score minimum pour entrer | `0.3` |
| `exit_threshold` | Score pour sortir | `-0.2` |
| `confirmation_candles` | Bougies de confirmation (anti-repainting) | `2` |
| `max_trades_per_day` | Maximum de trades par jour | `5` |
| `cooldown_minutes` | Délai entre les trades | `60` |

### Poids des indicateurs

Les 9 indicateurs et leur poids sont optimisés par Optuna :

| Indicateur | Description |
|------------|-------------|
| `ema` | Croisement EMA 50/200 |
| `macd` | Histogramme MACD |
| `rsi` | RSI (zones sur-achat/survente) |
| `stoch_rsi` | Stochastic RSI |
| `bollinger` | Position dans les bandes |
| `atr` | Volatilité (ATR) |
| `obv` | On Balance Volume |
| `fear_greed` | Fear & Greed Index |
| `user_indicator` | Indicateur manuel (fixé à 5%) |

**Note :** `user_indicator` est fixé à 5% et n'est pas optimisé. Il permet un ajustement manuel via le dashboard sans dominer la décision.

---

## Résolution de problèmes

### "DATABASE_URL not set"

```bash
# Vérifier que le fichier .env existe
cat .env

# Vérifier que les containers sont démarrés
docker compose ps
```

### "Not enough candles"

```bash
# Récupérer plus de données historiques
docker compose exec bot python -m main fetch \
  --symbol BTCUSDT --start-date 2023-01-01 --end-date 2025-01-01
```

### "Missing API credentials"

Vérifier le fichier `.env` :
```bash
# Pour testnet
BINANCE_TESTNET_API_KEY=xxx
BINANCE_TESTNET_API_SECRET=xxx

# Pour mainnet
BINANCE_MAINNET_API_KEY=xxx
BINANCE_MAINNET_API_SECRET=xxx
```

### "Connection refused" (Redis)

```bash
# Vérifier que Redis tourne
docker compose ps redis

# Redémarrer si nécessaire
docker compose restart redis
```

### Voir les logs du bot

```bash
# En temps réel
docker compose logs -f bot

# Les 100 dernières lignes
docker compose logs --tail 100 bot
```

### Redémarrer tout

```bash
docker compose down
docker compose up -d
```

---

## Structure des fichiers

```
/bot
├── main.py                 # Point d'entrée CLI unifié
├── scripts/
│   ├── fetch_historical_data.py  # Récupération données
│   ├── backtest.py              # CLI backtest
│   └── trading.py               # Boucle paper/live
├── exchanges/              # Connecteurs exchange
├── indicators/             # Calcul des indicateurs
├── strategy/               # Moteur de décision
├── backtesting/            # Moteurs de backtest
├── optimization/           # Optimisation Optuna
└── runs/                   # Gestion des runs
```

---

## Commandes Docker fréquentes

```bash
# Démarrer tout
docker compose up -d

# Arrêter tout
docker compose down

# Voir les logs
docker compose logs -f bot

# Exécuter une commande dans le bot
docker compose exec bot python -m main <commande>

# Accéder au shell du container
docker compose exec bot bash

# Redémarrer un service
docker compose restart bot

# Reconstruire les images
docker compose build
```

---

## Support

- **Documentation complète :** Voir `CLAUDE.md` à la racine du projet
- **Issues :** https://github.com/anthropics/claude-code/issues
- **Logs d'erreur :** Consultez la table `errors_log` dans la base de données
