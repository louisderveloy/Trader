# Optimization Module

Module d'optimisation Optuna pour l'optimisation des poids des indicateurs avec validation walk-forward.

## Vue d'ensemble

Ce module fournit un système complet d'optimisation basé sur Optuna pour trouver les poids optimaux des indicateurs techniques. L'optimisation utilise une analyse walk-forward pour garantir la robustesse des résultats sur des données out-of-sample.

### Caractéristiques principales

- **Walk-forward analysis** : Validation robuste avec splits train/test successifs
- **Optuna** : Framework d'optimisation bayésienne performant
- **Vectorbt** : Backtesting rapide pour des milliers d'itérations
- **Persistence database** : Sauvegarde automatique des résultats dans PostgreSQL
- **Multiple objectifs** : Sharpe, Sortino, profit factor, win rate, total return
- **CLI interface** : Lancement facile depuis la ligne de commande

## Architecture

```
optimization/
├── types.py           # Définitions de types (OptimizationConfig, StudyResult, etc.)
├── config.py          # Gestion de configuration
├── walk_forward.py    # Logique de walk-forward analysis
├── objective.py       # Fonction objectif pour Optuna
├── runner.py          # Orchestrateur d'optimisation
├── db.py              # Intégration base de données
├── cli.py             # Interface en ligne de commande
└── __init__.py        # Exports du module
```

## Types principaux

### OptimizationConfig

Configuration complète pour une étude d'optimisation :

```python
from optimization import OptimizationConfig, OptimizationObjective, WalkForwardMode

config = OptimizationConfig(
    study_name="my_optimization_study",
    objective=OptimizationObjective.SHARPE_RATIO,
    n_trials=100,
    walk_forward_mode=WalkForwardMode.SLIDING,
    n_splits=4,
    train_ratio=0.75,
    initial_capital=Decimal("10000.0"),
    symbol="BTCUSDT",
    timeframe="15m",
    start_date=datetime(2023, 1, 1),
    end_date=datetime(2024, 12, 31),
    sampler="tpe",
    pruner="median"
)
```

### WalkForwardSplit

Représente un split train/test unique :

```python
split = WalkForwardSplit(
    split_index=0,
    train_start=datetime(2023, 1, 1),
    train_end=datetime(2023, 9, 30),
    test_start=datetime(2023, 10, 1),
    test_end=datetime(2023, 12, 31)
)
```

### StudyResult

Résultat complet d'une étude d'optimisation :

```python
result = StudyResult(
    study_name="study_2024",
    run_id=UUID(...),
    n_trials=400,  # 100 trials × 4 splits
    best_value=2.15,  # Sharpe ratio
    best_params={
        "weight_ema": 0.14,
        "weight_macd": 0.22,
        # ...
    },
    best_weights={
        "ema": 0.14,
        "macd": 0.22,
        # ...
    },
    weights_set_id=UUID(...),
    started_at=datetime.now(),
    completed_at=datetime.now(),
    optimization_time_seconds=3625.5,
    walk_forward_results=[...],
    metadata={...}
)
```

## Walk-Forward Analysis

La walk-forward analysis divise les données en plusieurs périodes d'entraînement et de test successives pour valider la robustesse des poids optimisés.

### Mode Sliding Window

Fenêtres de taille fixe qui glissent dans le temps :

```
Split 1: [Train: Jan-Sep] [Test: Oct-Dec]
Split 2:         [Train: Apr-Dec] [Test: Jan-Mar]
Split 3:                 [Train: Jul-Mar] [Test: Apr-Jun]
Split 4:                         [Train: Oct-Jun] [Test: Jul-Sep]
```

### Mode Expanding Window

Fenêtre d'entraînement qui s'agrandit, fenêtre de test fixe :

```
Split 1: [Train: Jan-Sep]                    [Test: Oct-Dec]
Split 2: [Train: Jan-----Dec]                [Test: Jan-Mar]
Split 3: [Train: Jan----------Mar]           [Test: Apr-Jun]
Split 4: [Train: Jan---------------Jun]      [Test: Jul-Sep]
```

## Objectifs d'optimisation

| Objectif | Description | Recommandation |
|----------|-------------|----------------|
| `SHARPE_RATIO` | Ratio rendement/risque (défaut) | Bon compromis performance/risque |
| `SORTINO_RATIO` | Ratio basé sur la volatilité négative | Moins pénalisé par la volatilité haussière |
| `PROFIT_FACTOR` | Ratio gains/pertes | Maximise le profit brut |
| `WIN_RATE` | % de trades gagnants | Peut réduire le profit moyen |
| `TOTAL_RETURN` | Rendement total | Ignore le risque |

## Utilisation

### 1. Configuration depuis l'environnement

Variables d'environnement (optionnelles, avec défauts) :

```bash
OPTIMIZATION_STUDY_NAME="my_study"
OPTIMIZATION_OBJECTIVE="sharpe_ratio"
OPTIMIZATION_N_TRIALS="100"
OPTIMIZATION_WF_MODE="sliding"
OPTIMIZATION_N_SPLITS="4"
OPTIMIZATION_TRAIN_RATIO="0.75"
OPTIMIZATION_INITIAL_CAPITAL="10000.0"
OPTIMIZATION_SYMBOL="BTCUSDT"
OPTIMIZATION_TIMEFRAME="15m"
OPTIMIZATION_START_DATE="2023-01-01T00:00:00Z"
OPTIMIZATION_END_DATE="2024-12-31T23:59:59Z"
OPTIMIZATION_SAMPLER="tpe"
OPTIMIZATION_PRUNER="median"
OPTIMIZATION_STORAGE="postgresql://user:pass@localhost/optuna"
```

```python
from optimization import load_config_from_env

config = load_config_from_env()
```

### 2. Configuration programmatique

```python
from optimization import create_default_config
from datetime import datetime

config = create_default_config(
    study_name="backtest_2024",
    symbol="BTCUSDT",
    timeframe="15m",
    start_date=datetime(2023, 1, 1),
    end_date=datetime(2024, 12, 31)
)
```

### 3. Espace de recherche

Par défaut, tous les 9 indicateurs sont optimisés :

```python
from optimization import create_search_space

search_space = create_search_space()
# Optimise: ema, macd, rsi, stoch_rsi, bollinger, atr, obv, fear_greed, user_indicator

# Espace personnalisé
search_space = create_search_space(
    indicators=["ema", "macd", "rsi"],
    min_weight=0.0,
    max_weight=1.0,
    normalize=True  # Normalise les poids pour que la somme = 1.0
)
```

### 4. Lancement d'une optimisation

```python
from optimization.runner import OptimizationRunner
import asyncpg

# Connexion DB
db_pool = await asyncpg.create_pool(dsn="postgresql://...")

# Runner
runner = OptimizationRunner(config, db_pool)

# Lancement
result = await runner.run()

print(f"Best Sharpe: {result.best_value:.2f}")
print(f"Best weights: {result.best_weights}")
print(f"Weights set ID: {result.weights_set_id}")
```

## Samplers Optuna

| Sampler | Description | Usage recommandé |
|---------|-------------|------------------|
| `tpe` | Tree-structured Parzen Estimator | **Par défaut** - Bon pour paramètres continus |
| `random` | Recherche aléatoire | Baseline simple |
| `grid` | Grille exhaustive | Petit espace de recherche |
| `cmaes` | CMA-ES | Optimisation continue avancée |

## Pruners Optuna

| Pruner | Description | Usage recommandé |
|--------|-------------|------------------|
| `median` | Arrête les trials sous-performants | **Par défaut** - Bon compromis |
| `hyperband` | Allocation dynamique de ressources | Large espace de recherche |
| `none` | Pas de pruning | Petit nombre de trials |

## Persistence des résultats

Les résultats sont automatiquement sauvegardés dans la base de données :

### Table `weights_sets`

```sql
INSERT INTO weights_sets (name, source, weights, optimization_score, is_active)
VALUES (
  'Optuna Study #42',
  'optuna',
  '{"ema": 0.14, "macd": 0.22, ...}',
  2.15,
  false
);
```

### Table `optuna_studies`

```sql
INSERT INTO optuna_studies (
  study_name, n_trials, best_value, best_params,
  weights_set_id, started_at, completed_at, metadata
)
VALUES (
  'study_2024',
  400,
  2.15,
  '{"weight_ema": 0.14, ...}',
  '...',
  '2024-01-01 10:00:00',
  '2024-01-01 11:00:00',
  '{...}'
);
```

## Activation des poids optimisés

Une fois l'optimisation terminée, activez le set de poids depuis le dashboard :

```sql
-- Désactiver tous les sets
UPDATE weights_sets SET is_active = false;

-- Activer le set optimal
UPDATE weights_sets SET is_active = true WHERE id = '...';
```

Le bot utilisera automatiquement les poids actifs au prochain run.

## Métriques de sortie

Chaque optimisation produit :

- **Best value** : Meilleure valeur de l'objectif (ex: Sharpe = 2.15)
- **Best params** : Meilleurs paramètres trouvés (poids bruts)
- **Best weights** : Poids normalisés pour utilisation
- **Walk-forward results** : Scores train/test pour chaque split
- **Optimization time** : Temps total d'optimisation
- **N trials** : Nombre de trials exécutés

## Convergence et validation

### Critères de convergence

Une optimisation est réussie si :

1. **Stabilité** : Les 10 derniers trials ne s'améliorent plus significativement
2. **Robustesse** : Score test ≈ score train (pas d'overfitting)
3. **Cohérence** : Scores similaires entre les splits walk-forward

### Détection d'overfitting

**Indicateurs d'overfitting** :
- Score train >> score test (ex: train=2.5, test=1.2)
- Grande variance entre splits
- Poids extrêmes (proche de 0 ou 1)

**Solutions** :
- Augmenter la taille de la fenêtre de test
- Réduire le nombre de paramètres optimisés
- Ajouter de la régularisation

## CLI Interface

### Lancer une optimisation

```bash
python -m optimization.cli run \
  --study-name "my_study" \
  --n-trials 100 \
  --objective sharpe_ratio \
  --n-splits 4 \
  --symbol BTCUSDT \
  --timeframe 15m \
  --start-date 2023-01-01 \
  --end-date 2024-12-31
```

### Lister les études

```bash
python -m optimization.cli list
```

### Reprendre une étude

```bash
python -m optimization.cli resume --study-name "my_study"
```

### Afficher le meilleur résultat

```bash
python -m optimization.cli best --study-name "my_study"
```

## Exemples

### Exemple 1 : Optimisation rapide sur 1 an

```python
config = create_default_config(
    study_name="quick_test",
    symbol="BTCUSDT",
    timeframe="1h",
    start_date=datetime(2024, 1, 1),
    end_date=datetime(2024, 12, 31)
)
config.n_trials = 50
config.n_splits = 2

runner = OptimizationRunner(config, db_pool)
result = await runner.run()
```

### Exemple 2 : Optimisation complète multi-années

```python
config = create_default_config(
    study_name="full_optimization",
    symbol="BTCUSDT",
    timeframe="15m",
    start_date=datetime(2022, 1, 1),
    end_date=datetime(2024, 12, 31)
)
config.n_trials = 200
config.n_splits = 6
config.walk_forward_mode = WalkForwardMode.EXPANDING

runner = OptimizationRunner(config, db_pool)
result = await runner.run()
```

### Exemple 3 : Optimisation sur indicateurs spécifiques

```python
search_space = create_search_space(
    indicators=["ema", "macd", "rsi", "atr"],  # Seulement 4 indicateurs
    min_weight=0.1,  # Minimum 10% par indicateur
    max_weight=0.4,  # Maximum 40% par indicateur
    normalize=True
)

# Passer le search_space au runner (à implémenter dans runner.py)
```

## Tests

```bash
# Tests unitaires
docker compose exec bot sh -c "python -m pytest tests/test_optimization*.py -v"

# Tests avec coverage
docker compose exec bot sh -c "python -m pytest tests/test_optimization*.py --cov=optimization --cov-report=term-missing -v"

# Test spécifique
docker compose exec bot sh -c "python -m pytest tests/test_walk_forward.py -v"
```

## Logging

Tous les logs sont structurés au format JSON :

```python
logger.info(
    "Optimization started",
    extra={
        "study_name": "my_study",
        "n_trials": 100,
        "objective": "sharpe_ratio"
    }
)
```

## Références

- [Optuna Documentation](https://optuna.readthedocs.io/)
- [Walk-Forward Analysis](https://en.wikipedia.org/wiki/Walk_forward_analysis)
- [Sharpe Ratio](https://en.wikipedia.org/wiki/Sharpe_ratio)
- [Vectorbt Documentation](https://vectorbt.dev/)
