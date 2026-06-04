# Backtesting Module

Module de backtesting pour le bot de trading crypto avec deux implémentations obligatoires.

## Vue d'ensemble

Ce module fournit deux moteurs de backtesting qui doivent être utilisés de manière complémentaire :

1. **vectorbt** : Backtesting vectorisé rapide pour l'optimisation Optuna
2. **event-driven** : Backtesting événementiel pour la validation finale (simulation exacte du trading live)

### Règle de cohérence

Les deux moteurs doivent produire des résultats cohérents sur la même configuration :
- **Tolérance P&L** : <2% de différence acceptable
- **Validation obligatoire** : Tout écart >2% doit être investigué

## Architecture

```
backtesting/
  ├── types.py              # Types et dataclasses
  ├── base.py               # Interface abstraite BacktesterBase
  ├── vectorbt_engine.py    # Implémentation vectorbt
  ├── event_driven.py       # Implémentation event-driven
  ├── metrics.py            # Calcul des métriques standardisées
  ├── coherence.py          # Validation de cohérence
  ├── __init__.py           # Exports du module
  └── README.md             # Cette documentation
```

## Types principaux

### BacktestConfig

Configuration pour un run de backtest :

```python
from backtesting import BacktestConfig
from datetime import datetime
from decimal import Decimal

config = BacktestConfig(
    start_date=datetime(2024, 1, 1),
    end_date=datetime(2024, 12, 31),
    initial_capital=Decimal("10000"),
    symbol="BTC/USDT",
    timeframe="15m",
    commission_rate=Decimal("0.001"),  # 0.1%
    slippage_pct=Decimal("0.002"),  # 0.2%
    weights_set_id=uuid.UUID("..."),  # UUID du set de poids actif
)
```

### BacktestResult

Résultat complet d'un backtest :

```python
result = await backtester.run()

print(f"Mode: {result.mode}")
print(f"Total trades: {result.metrics.total_trades}")
print(f"Win rate: {result.metrics.win_rate:.2f}%")
print(f"Total P&L: {result.metrics.total_pnl} USDT")
print(f"Sharpe ratio: {result.metrics.sharpe_ratio:.2f}")
print(f"Max drawdown: {result.metrics.max_drawdown_pct:.2f}%")
```

### BacktestMetrics

Métriques de performance standardisées :

- **Performance de base** : Total return, P&L, capital final
- **Statistiques de trades** : Nombre de trades, win rate, avg win/loss
- **Métriques de risque** : Sharpe, Sortino, max drawdown, Calmar ratio
- **Exposition** : % du temps en position, durée moyenne
- **Comparaison buy-and-hold** : Return B&H, excess return

## Utilisation

### 1. Backtesting vectorbt (rapide)

Utilisé pour l'optimisation Optuna (nombreuses itérations) :

```python
from backtesting.vectorbt_engine import VectorbtBacktester
import asyncpg

# Configuration
config = BacktestConfig(...)

# Connexion DB pour charger les données
db_pool = await asyncpg.create_pool(...)

# Créer et exécuter le backtester
backtester = VectorbtBacktester(config, db_pool)
result = await backtester.run()

print(f"Sharpe ratio: {result.metrics.sharpe_ratio:.2f}")
print(f"Execution time: {result.execution_time_seconds:.2f}s")
```

### 2. Backtesting event-driven (validation)

Utilisé pour la validation finale avant le passage en live :

```python
from backtesting.event_driven import EventDrivenBacktester

# Même configuration que vectorbt
config = BacktestConfig(...)

# Créer et exécuter le backtester
backtester = EventDrivenBacktester(config, db_pool)
result = await backtester.run()

print(f"Total trades: {result.metrics.total_trades}")
print(f"Final capital: {result.metrics.final_capital}")
```

### 3. Validation de cohérence

Comparer les résultats des deux moteurs :

```python
from backtesting.coherence import validate_coherence

# Exécuter les deux backtests
vectorbt_result = await vectorbt_backtester.run()
event_driven_result = await event_driven_backtester.run()

# Valider la cohérence
coherence = validate_coherence(vectorbt_result, event_driven_result)

if coherence.is_coherent:
    print("✅ Results are coherent (<2% difference)")
else:
    print(f"❌ Results differ by {coherence.pnl_difference_pct:.2f}%")
    print(f"Differences: {coherence.differences}")
```

## Métriques calculées

### Sharpe Ratio
```
Sharpe = (Mean Return - Risk-Free Rate) / Std Dev of Returns
```
Annualisé pour comparaison avec d'autres stratégies.

### Sortino Ratio
```
Sortino = (Mean Return - Risk-Free Rate) / Downside Deviation
```
Comme le Sharpe mais ne pénalise que la volatilité négative.

### Max Drawdown
```
Max DD = Max(Peak - Trough) / Peak
```
Perte maximale depuis un plus-haut historique.

### Win Rate
```
Win Rate = Winning Trades / Total Trades * 100
```

### Profit Factor
```
Profit Factor = Total Wins / |Total Losses|
```
Un ratio >1 indique une stratégie rentable.

### Calmar Ratio
```
Calmar = Total Return / Max Drawdown
```
Mesure du return ajusté au risque de drawdown.

## Différences entre les deux moteurs

| Aspect | vectorbt | event-driven |
|--------|----------|--------------|
| **Performance** | Très rapide (vectorisé) | Plus lent (boucle événementielle) |
| **Précision** | Approximative (assume fill instantané) | Exacte (simule latence, slippage, timeouts) |
| **Usage** | Optimisation Optuna | Validation finale |
| **Ordres limites** | Non simulés | Simulés avec timeout → market fallback |
| **Slippage** | Forfaitaire sur tous les trades | Simulé dynamiquement selon liquidité |
| **Latence** | Ignorée | Simulée (délai entre signal et exécution) |
| **Complexité code** | Simple (utilise vectorbt lib) | Complexe (implémentation custom) |

## Workflow recommandé

```
1. Développement stratégie
   ↓
2. Backtesting rapide avec vectorbt (ajustements itératifs)
   ↓
3. Optimisation Optuna avec vectorbt (trouver meilleurs poids)
   ↓
4. Validation avec event-driven (sur les meilleurs poids trouvés)
   ↓
5. Vérification cohérence (<2% diff)
   ↓
6. Si cohérent : passage en paper trading
   ↓
7. Si incohérent : investigation et correction
```

## Intégration avec la base de données

Les backtests créent des entrées dans la table `runs` avec :
- `run_type = 'backtest'`
- `mode = 'vectorbt'` ou `mode = 'event_driven'`
- Snapshot complet de la configuration
- Référence au `weights_set_id` utilisé

Les trades sont sauvegardés dans la table `trades` avec le `run_id` associé.

## Logging

Tous les logs sont structurés en JSON (pas de `print()`) :

```python
logger.info(
    "Backtest completed",
    extra={
        "mode": result.mode.value,
        "trades": result.metrics.total_trades,
        "pnl": float(result.metrics.total_pnl),
        "sharpe": result.metrics.sharpe_ratio,
        "execution_time_seconds": result.execution_time_seconds
    }
)
```

## Tests

Tests unitaires couvrant :
- `test_backtesting_types.py` : Validation des types et dataclasses
- `test_backtesting_metrics.py` : Calcul des métriques avec inputs/outputs connus
- `test_backtesting_vectorbt.py` : Moteur vectorbt
- `test_backtesting_event_driven.py` : Moteur event-driven
- `test_backtesting_coherence.py` : Validation de cohérence

Objectif de couverture : >70% (minimum), >80% (cible).

## Références

- vectorbt documentation : https://vectorbt.dev/
- CLAUDE.md Phase 5 spécifications
- docs/A2_config_params.md : Paramètres de backtesting configurables
- docs/A3_snapshots_format.md : Format des snapshots
