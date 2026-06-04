"""
Optimization module for indicator weight optimization using Optuna.

This module provides a complete optimization system with:
- Walk-forward analysis for robust out-of-sample validation
- Optuna-based hyperparameter optimization
- Integration with vectorbt backtester for fast iterations
- Database persistence of optimization results
- CLI interface for running optimizations
"""

from .types import (
    OptimizationObjective,
    WalkForwardMode,
    WalkForwardSplit,
    WalkForwardResult,
    OptimizationConfig,
    StudyResult,
    WeightsSearchSpace
)

from .config import (
    load_config_from_env,
    create_default_config,
    validate_config,
    create_search_space
)

from .walk_forward import (
    generate_splits,
    generate_splits_from_db,
    get_data_date_range
)

from .objective import (
    ObjectiveFunction,
    create_objective_function,
    evaluate_weights
)

from .runner import (
    OptimizationRunner,
    run_optimization
)

from .db import (
    save_weights_set,
    save_study_result,
    get_active_weights,
    list_weights_sets,
    get_study_by_name,
    list_studies,
    activate_weights_set
)

__all__ = [
    # Types
    "OptimizationObjective",
    "WalkForwardMode",
    "WalkForwardSplit",
    "WalkForwardResult",
    "OptimizationConfig",
    "StudyResult",
    "WeightsSearchSpace",
    # Config
    "load_config_from_env",
    "create_default_config",
    "validate_config",
    "create_search_space",
    # Walk-forward
    "generate_splits",
    "generate_splits_from_db",
    "get_data_date_range",
    # Objective
    "ObjectiveFunction",
    "create_objective_function",
    "evaluate_weights",
    # Runner
    "OptimizationRunner",
    "run_optimization",
    # Database
    "save_weights_set",
    "save_study_result",
    "get_active_weights",
    "list_weights_sets",
    "get_study_by_name",
    "list_studies",
    "activate_weights_set",
]
