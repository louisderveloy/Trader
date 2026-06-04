# CLAUDE.md — Bot de Trading Crypto

## Vue d'ensemble du projet

Bot de trading crypto automatisé pour Binance (BTC/USDT en v1), avec backtesting, optimisation des poids par Optuna, dashboard de configuration Vue.js et visualisation Grafana. Projet solo, mono-utilisateur v1.

---

## Architecture globale

```
┌─────────────────────────────────────────────────────────────────┐
│                         Traefik (reverse proxy + HTTPS)         │
│              ForwardAuth JWT → auth unifiée Vue.js + Grafana    │
└────────────┬───────────────────┬───────────────────┬────────────┘
             │                   │                   │
     bot.localhost        api.localhost     grafana.localhost
     (Vue.js)             (FastAPI)         (Grafana)
                               │
                          Redis pub/sub
                               │
                           Bot Python
                               │
                    PostgreSQL + TimescaleDB
```

### Règle fondamentale de communication
- Le bot publie ses événements sur Redis (jamais d'appel HTTP synchrone vers l'API).
- L'API consomme Redis et expose les données au dashboard.
- Le dashboard envoie des commandes via l'API → Redis → bot.
- Le bot continue de tourner même si l'API ou le dashboard est down.

---

## Structure du monorepo

```
/bot              → code Python du bot de trading
  /exchanges      → connecteurs exchange (interface abstraite ExchangeBase, impl. Binance)
  /indicators     → un fichier par indicateur
  /strategy       → moteur de décision et scoring
  /optimization   → runner Optuna + walk-forward analysis
  /notifications  → Discord webhook
  /backtesting    → backtester vectorbt + event-driven custom
/api              → backend FastAPI
/dashboard        → frontend Vue.js
/grafana          → dashboards JSON versionnés + provisionning
/db               → migrations Alembic
/docker           → Dockerfiles
/docs             → documentation technique et annexes
docker-compose.yml          → dev local
docker-compose.prod.yml     → production VPS
.env.example                → toutes les variables documentées
```

---

## Stack technique

| Composant | Technologie |
|---|---|
| Bot trading | Python 3.13 |
| Backend API | FastAPI |
| Frontend dashboard | Vue 3 + Vite + Pinia + Vue Router + TailwindCSS |
| Visualisation | Grafana (connecté PostgreSQL/TimescaleDB) |
| Base de données | PostgreSQL + extension TimescaleDB |
| Cache / messaging | Redis (pub/sub + queue) |
| Reverse proxy | Traefik |
| Optimisation | Optuna |
| Backtesting rapide | vectorbt |
| Backtesting validation | custom event-driven |
| Migrations DB | Alembic |
| Linting Python | ruff |
| Linting JS | eslint |
| Tests Python | pytest |
| CI/CD | GitHub Actions |
| Conteneurisation | Docker + docker-compose |

---

## Exchange & trading

- **Exchange** : Binance uniquement (v1). Interface abstraite `ExchangeBase` prévue pour extension.
- **Paires** : BTC/USDT (v1), architecture multi-paires prévue.
- **Timeframe principal** : 15m (ajustable via config).
- **Ordres** : limite post-only par défaut, fallback market après timeout (30 min par défaut, configurable).
- **Slippage max** : 0.2% (configurable).
- **Mode** : testnet d'abord (toggle `BINANCE_TESTNET=true/false` dans `.env`).

---

## Indicateurs techniques

Chaque indicateur est dans `/bot/indicators/<nom>.py` et expose :
- `compute(candles, params) -> values`
- `to_signal(values) -> float ∈ [-1, 1]` (normalisation obligatoire)

| Fichier | Indicateur | Paramètres clés |
|---|---|---|
| `ema.py` | EMA 50 / EMA 200 | périodes configurables |
| `macd.py` | MACD | fast, slow, signal configurables |
| `rsi.py` | RSI | période, seuils sur/sous-achat configurables |
| `stoch_rsi.py` | Stochastic RSI | périodes configurables |
| `bollinger.py` | Bollinger Bands | période, std dev configurables |
| `atr.py` | ATR | période configurable |
| `obv.py` | OBV | — |
| `fear_greed.py` | Fear & Greed Index | source : alternative.me |
| `user_indicator.py` | Indicateur utilisateur | slider -1/+1, note, expiration, loggé |

---

## Moteur de stratégie

- **Score pondéré** = Σ (signal_i × poids_i), résultat ∈ [-1, 1]
- **Poids** : optimisés par Optuna, versionnés en DB dans `weights_sets`, activables depuis le dashboard
- **Seuils** d'entrée et sortie : configurables depuis le dashboard
- **Anti-repainting** : confirmation sur N bougies (configurable)
- **Quotas** : nb max trades/jour, exposition max (configurables)
- **Cooldown** post-trade : configurable
- **Stop-loss / take-profit** : ATR-based ou fixes (configurable)
- Toute décision est loggée avec snapshot complet (poids actifs, valeurs indicateurs, raison de la décision ou du skip)

### Modes de sizing (configurables depuis le dashboard)
1. **Fixe** : montant fixe par trade
2. **Confiance** : proportionnel au score pondéré
3. **Risk-based ATR** : sizing selon ATR et % de capital à risquer

---

## Base de données — Schéma principal

Tables clés (voir `/docs/A1_ERD.md` pour le schéma complet) :

| Table | Description |
|---|---|
| `runs` | Chaque exécution (backtest / optim / paper / live) avec snapshot params |
| `candles` | Hypertable TimescaleDB : OHLCV par symbol + timeframe |
| `indicators_values` | Valeurs et signaux calculés par run |
| `user_indicator` | Valeurs de l'indicateur utilisateur avec expiration |
| `signals` | Décisions du bot avec score et snapshot des poids |
| `orders` | Ordres passés avec statut et id exchange |
| `trades` | Trades complétés avec P&L |
| `weights_sets` | Sets de poids (source Optuna ou manuel), activables |
| `optuna_studies` | Résultats des études d'optimisation |
| `users` | Mono-utilisateur v1, prévu multi pour Grafana (migration Option B) |
| `notifications_log` | Historique des notifications Discord |
| `errors_log` | Erreurs et exceptions |

### Règles DB
- **Rien n'est jamais supprimé** (soft delete si nécessaire, jamais de DELETE).
- Tout événement porte un `run_id`.
- Snapshots de config au démarrage de chaque run.
- Continuous aggregates TimescaleDB pour P&L journalier.

---

## Backtesting

### Deux saveurs obligatoires
1. **vectorbt** : pour les runs d'optimisation Optuna (rapide, vectorisé)
2. **Custom event-driven** : pour la validation finale (simule exactement le live : slippage, frais, latence, ordres limites)

### Règle de cohérence
Les deux backtesteurs doivent donner des résultats cohérents sur la même config (tolérance <2% sur le P&L). Tout écart >2% doit être investigué.

### Métriques de sortie standardisées
Sharpe, Sortino, max drawdown, win rate, profit factor, exposition, comparaison automatique vs buy-and-hold BTC.

---

## Optimisation Optuna

- Espace de recherche : poids des 8 indicateurs minimum (extensible)
- Objectif par défaut : maximiser le ratio de Sharpe
- **Walk-forward analysis** obligatoire (splits train/test glissants)
- Résultats sauvegardés dans `weights_sets` avec score
- Activation d'un set de poids depuis le dashboard
- Déclenchement depuis le dashboard ou CLI

---

## Dashboard Vue.js

### Philosophie (règle stricte)
- Vue.js = **configuration + actions uniquement**
- Vue.js ne **développe pas** de graphes complexes
- Les visualisations complexes = **iframes Grafana** intégrées quand pertinent
- Les données simples = chiffres bruts (P&L du jour, dernière décision, état bot)

### Stack Vue.js
- Vue 3 (Composition API)
- Vite
- Pinia (state management)
- Vue Router
- TailwindCSS — **thème clair uniquement**

### Pages
| Page | Contenu |
|---|---|
| Login | Auth JWT |
| Accueil | État bot, P&L jour/semaine, dernière décision, iframe équity curve Grafana |
| Configuration | Tous les paramètres configurables, tooltips FR obligatoires |
| Indicateur utilisateur | Sliders par crypto, note, expiration |
| Runs | Liste backtests/optims/live, liens Grafana |
| Optimisations | Lancer étude Optuna, voir résultats, activer set de poids |
| Trades | Historique avec filtres, lien Grafana pour analyse |
| Logs & erreurs | Visualisation rapide |

### Règle composants
- Composant réutilisable `<ConfigField>` avec prop `tooltip` obligatoire
- **Tout paramètre configurable doit avoir un tooltip en français**
- Validation côté front ET côté back obligatoire

---

## Grafana

### Rôle
- Visualisation et analyse uniquement (jamais de config ni d'actions)
- Connecté directement à PostgreSQL/TimescaleDB

### Dashboards versionnés (JSON dans `/grafana/`)
| Dashboard | Contenu |
|---|---|
| P&L global | Équity curve, drawdown, perf vs buy-and-hold |
| Trades | Tableau filtrable, distribution P&L, heatmap par heure/jour |
| Run détail | Équity + indicateurs + signaux + trades sur un `run_id` |
| Comparaison runs | Superposition plusieurs `run_id` |
| Replay | Curseur temporel sur un run |
| Optimisations Optuna | Parallel coordinates, importance des paramètres |
| Santé bot | Latence, erreurs, ordres rejetés |

### Configuration
- Provisionning automatique datasources + dashboards au démarrage Docker
- **Mode anonyme** (auth gérée en amont par Traefik ForwardAuth)
- Thème clair (cohérence avec Vue.js)

---

## Authentification

### Architecture actuelle (Option A)
```
Navigateur → Traefik ForwardAuth (vérifie JWT) → Vue.js / Grafana
```
- JWT généré par FastAPI au login
- Grafana en mode anonyme derrière Traefik ForwardAuth
- Un seul login pour tout

### Migration future (Option B — multi-comptes Grafana)
- Traefik injecte header `X-Webauth-User` après vérif JWT
- Grafana auth proxy lit le header et crée/connecte l'utilisateur
- Procédure documentée dans `/docs/A5_auth_migration.md`

---

## Environnements

### Dev local
- Sous-domaines : `bot.localhost`, `api.localhost`, `grafana.localhost`
- HTTPS local via mkcert
- Binance testnet (`BINANCE_TESTNET=true`)
- `docker-compose.yml`

### Production VPS
- Sous-domaines : `bot.tondomaine.fr`, `api.tondomaine.fr`, `grafana.tondomaine.fr`
- HTTPS via Traefik + Let's Encrypt (auto)
- `docker-compose.prod.yml`
- Secrets uniquement via variables d'environnement (jamais dans le repo)
- Backups PostgreSQL automatiques (cron + dump compressé)

---

## Notifications Discord

- Module `/bot/notifications/discord.py`
- Événements notifiés (activables/désactivables depuis le dashboard) :
  - Trade ouvert / fermé (avec P&L)
  - Erreur critique (ordre rejeté, connexion perdue, exception non gérée)
  - Bot bloqué / quota atteint
  - Optimisation terminée
- Rate limiting intégré (anti-spam)
- Latence cible : <5s après l'événement

---

## Conventions de code

### Python (bot + API)
- Python 3.13
- Linter : `ruff` (configuration dans `pyproject.toml`)
- Type hints obligatoires sur toutes les fonctions publiques
- Docstrings obligatoires sur les classes et fonctions publiques
- Logs structurés JSON (jamais de `print()`)
- Pas d'appel HTTP synchrone depuis le bot vers l'API

### JavaScript/Vue.js
- Vue 3 Composition API uniquement (pas d'Options API)
- Linter : eslint
- Pas de graphes complexes développés en Vue.js

### Git
- Branches : `main` (stable), `dev` (développement), `feature/<nom>`
- Commits : préfixe conventionnel (`feat:`, `fix:`, `chore:`, `docs:`)
- Jamais de secrets dans le repo (vérification CI)

---

## Tests

- Framework : pytest (Python), vitest (Vue.js)
- Coverage cible : >70% sur le code métier
- Tests unitaires obligatoires : indicateurs, stratégie, sizing, anti-repainting
- Tests d'intégration : connecteur Binance mocké, pipeline complet sur data fixture
- Tests end-to-end : backtest reproductible (même seed = même résultat)
- CI GitHub Actions : lint + tests sur chaque PR

---

## Phases du projet

| Phase | Description |
|---|---|
| 0 | Setup projet & infrastructure de dev |
| 1 | Socle base de données |
| 2 | Connecteur Binance |
| 3 | Moteur d'indicateurs |
| 4 | Moteur de stratégie |
| 5 | Moteur de backtest |
| 6 | Module d'optimisation Optuna |
| 7 | Logging exhaustif & système de runs |
| 8 | API backend FastAPI + Redis |
| 9 | Dashboard Vue.js |
| 10 | Dashboards Grafana |
| 11 | Notifications Discord |
| 12 | Tests automatisés |
| 13 | Déploiement VPS prod |
| 14 | Paper trading prolongé (4-8 semaines minimum) |
| 15 | Passage live (capital initial limité, montée progressive) |

---

## Annexes (dans /docs/)

| Fichier | Contenu |
|---|---|
| `A1_ERD.md` | Schéma DB complet (ERD) |
| `A2_config_params.md` | Liste exhaustive des paramètres configurables avec tooltip FR |
| `A3_snapshots_format.md` | Format JSON des snapshots de config et de poids |
| `A4_traefik_topology.md` | Topologie réseau Traefik + sous-domaines |
| `A5_auth_migration.md` | Procédure migration auth Option A → Option B |
| `A6_runbook.md` | Procédures opérationnelles (redémarrage bot, restauration backup, rollback config) |

---

## Objectif principal

**Battre le buy-and-hold BTC sur 1 an de trading live.**
Évaluation formelle à 12 mois après le passage en Phase 15.
