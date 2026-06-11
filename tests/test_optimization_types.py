"""
Unit tests for optimization types.

This module tests all type definitions, dataclasses, enums, and validation
from the optimization.types module.
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from optimization.types import (
    OptimizationObjective,
    WalkForwardMode,
    WalkForwardSplit,
    WalkForwardResult,
    OptimizationConfig,
    StudyResult,
    WeightsSearchSpace
)


class TestOptimizationObjective:
    """Tests for OptimizationObjective enum."""

    def test_all_objectives_defined(self):
        """Test all optimization objectives are defined."""
        assert OptimizationObjective.SHARPE_RATIO == "sharpe_ratio"
        assert OptimizationObjective.SORTINO_RATIO == "sortino_ratio"
        assert OptimizationObjective.PROFIT_FACTOR == "profit_factor"
        assert OptimizationObjective.WIN_RATE == "win_rate"
        assert OptimizationObjective.TOTAL_RETURN == "total_return"

    def test_enum_membership(self):
        """Test enum membership checks."""
        assert "sharpe_ratio" in [obj.value for obj in OptimizationObjective]
        assert "invalid_objective" not in [obj.value for obj in OptimizationObjective]


class TestWalkForwardMode:
    """Tests for WalkForwardMode enum."""

    def test_all_modes_defined(self):
        """Test all walk-forward modes are defined."""
        assert WalkForwardMode.SLIDING == "sliding"
        assert WalkForwardMode.EXPANDING == "expanding"


class TestWalkForwardSplit:
    """Tests for WalkForwardSplit dataclass."""

    def test_create_valid_split(self):
        """Test creating a valid walk-forward split."""
        split = WalkForwardSplit(
            split_index=0,
            train_start=datetime(2023, 1, 1),
            train_end=datetime(2023, 9, 30),
            test_start=datetime(2023, 10, 1),
            test_end=datetime(2023, 12, 31)
        )

        assert split.split_index == 0
        assert split.train_start == datetime(2023, 1, 1)
        assert split.train_end == datetime(2023, 9, 30)
        assert split.test_start == datetime(2023, 10, 1)
        assert split.test_end == datetime(2023, 12, 31)

    def test_to_dict(self):
        """Test conversion to dictionary."""
        split = WalkForwardSplit(
            split_index=0,
            train_start=datetime(2023, 1, 1),
            train_end=datetime(2023, 9, 30),
            test_start=datetime(2023, 10, 1),
            test_end=datetime(2023, 12, 31)
        )

        split_dict = split.to_dict()

        assert split_dict["split_index"] == 0
        assert split_dict["train_start"] == "2023-01-01T00:00:00"
        assert split_dict["train_end"] == "2023-09-30T00:00:00"
        assert split_dict["test_start"] == "2023-10-01T00:00:00"
        assert split_dict["test_end"] == "2023-12-31T00:00:00"

    def test_invalid_train_dates(self):
        """Test validation fails if train_start >= train_end."""
        with pytest.raises(ValueError, match="train_start must be before train_end"):
            WalkForwardSplit(
                split_index=0,
                train_start=datetime(2023, 9, 30),
                train_end=datetime(2023, 1, 1),  # Before start
                test_start=datetime(2023, 10, 1),
                test_end=datetime(2023, 12, 31)
            )

    def test_invalid_test_dates(self):
        """Test validation fails if test_start >= test_end."""
        with pytest.raises(ValueError, match="test_start must be before test_end"):
            WalkForwardSplit(
                split_index=0,
                train_start=datetime(2023, 1, 1),
                train_end=datetime(2023, 9, 30),
                test_start=datetime(2023, 12, 31),
                test_end=datetime(2023, 10, 1)  # Before start
            )

    def test_invalid_train_test_overlap(self):
        """Test validation fails if train_end >= test_start."""
        with pytest.raises(ValueError, match="train_end must be before test_start"):
            WalkForwardSplit(
                split_index=0,
                train_start=datetime(2023, 1, 1),
                train_end=datetime(2023, 11, 1),  # After test start
                test_start=datetime(2023, 10, 1),
                test_end=datetime(2023, 12, 31)
            )


class TestWalkForwardResult:
    """Tests for WalkForwardResult dataclass."""

    def test_create_valid_result(self):
        """Test creating a valid walk-forward result."""
        split = WalkForwardSplit(
            split_index=0,
            train_start=datetime(2023, 1, 1),
            train_end=datetime(2023, 9, 30),
            test_start=datetime(2023, 10, 1),
            test_end=datetime(2023, 12, 31)
        )

        result = WalkForwardResult(
            split=split,
            train_score=2.15,
            test_score=1.98,
            best_params={"weight_ema": 0.15, "weight_macd": 0.20},
            n_trials=100,
            optimization_time_seconds=125.5
        )

        assert result.split == split
        assert result.train_score == 2.15
        assert result.test_score == 1.98
        assert result.best_params == {"weight_ema": 0.15, "weight_macd": 0.20}
        assert result.n_trials == 100
        assert result.optimization_time_seconds == 125.5

    def test_to_dict(self):
        """Test conversion to dictionary."""
        split = WalkForwardSplit(
            split_index=0,
            train_start=datetime(2023, 1, 1),
            train_end=datetime(2023, 9, 30),
            test_start=datetime(2023, 10, 1),
            test_end=datetime(2023, 12, 31)
        )

        result = WalkForwardResult(
            split=split,
            train_score=2.15,
            test_score=1.98,
            best_params={"weight_ema": 0.15},
            n_trials=100,
            optimization_time_seconds=125.5
        )

        result_dict = result.to_dict()

        assert "split" in result_dict
        assert result_dict["train_score"] == 2.15
        assert result_dict["test_score"] == 1.98
        assert result_dict["best_params"] == {"weight_ema": 0.15}
        assert result_dict["n_trials"] == 100
        assert result_dict["optimization_time_seconds"] == 125.5


class TestOptimizationConfig:
    """Tests for OptimizationConfig dataclass."""

    def test_create_default_config(self):
        """Test creating config with default values."""
        config = OptimizationConfig(study_name="test_study")

        assert config.study_name == "test_study"
        assert config.objective == OptimizationObjective.SHARPE_RATIO
        assert config.n_trials == 100
        assert config.walk_forward_mode == WalkForwardMode.SLIDING
        assert config.n_splits == 4
        assert config.train_ratio == 0.75
        assert config.initial_capital == Decimal("10000.0")
        assert config.symbol == "BTCUSDT"
        assert config.timeframe == "15m"
        assert config.sampler == "tpe"
        assert config.pruner == "median"

    def test_create_custom_config(self):
        """Test creating config with custom values."""
        config = OptimizationConfig(
            study_name="custom_study",
            objective=OptimizationObjective.SORTINO_RATIO,
            n_trials=200,
            walk_forward_mode=WalkForwardMode.EXPANDING,
            n_splits=6,
            train_ratio=0.8,
            initial_capital=Decimal("50000.0"),
            symbol="ETHUSDT",
            timeframe="1h",
            sampler="cmaes",
            pruner="hyperband"
        )

        assert config.study_name == "custom_study"
        assert config.objective == OptimizationObjective.SORTINO_RATIO
        assert config.n_trials == 200
        assert config.walk_forward_mode == WalkForwardMode.EXPANDING
        assert config.n_splits == 6
        assert config.train_ratio == 0.8
        assert config.initial_capital == Decimal("50000.0")
        assert config.symbol == "ETHUSDT"
        assert config.timeframe == "1h"
        assert config.sampler == "cmaes"
        assert config.pruner == "hyperband"

    def test_invalid_n_trials(self):
        """Test validation fails for invalid n_trials."""
        with pytest.raises(ValueError, match="n_trials must be positive"):
            OptimizationConfig(study_name="test", n_trials=0)

        with pytest.raises(ValueError, match="n_trials must be positive"):
            OptimizationConfig(study_name="test", n_trials=-10)

    def test_invalid_n_splits(self):
        """Test validation fails for invalid n_splits."""
        with pytest.raises(ValueError, match="n_splits must be positive"):
            OptimizationConfig(study_name="test", n_splits=0)

    def test_invalid_train_ratio(self):
        """Test validation fails for invalid train_ratio."""
        with pytest.raises(ValueError, match="train_ratio must be in \\(0, 1\\)"):
            OptimizationConfig(study_name="test", train_ratio=0.0)

        with pytest.raises(ValueError, match="train_ratio must be in \\(0, 1\\)"):
            OptimizationConfig(study_name="test", train_ratio=1.0)

        with pytest.raises(ValueError, match="train_ratio must be in \\(0, 1\\)"):
            OptimizationConfig(study_name="test", train_ratio=-0.5)

        with pytest.raises(ValueError, match="train_ratio must be in \\(0, 1\\)"):
            OptimizationConfig(study_name="test", train_ratio=1.5)

    def test_invalid_initial_capital(self):
        """Test validation fails for invalid initial_capital."""
        with pytest.raises(ValueError, match="initial_capital must be positive"):
            OptimizationConfig(study_name="test", initial_capital=Decimal("0"))

        with pytest.raises(ValueError, match="initial_capital must be positive"):
            OptimizationConfig(study_name="test", initial_capital=Decimal("-1000"))

    def test_invalid_dates(self):
        """Test validation fails for invalid start/end dates."""
        with pytest.raises(ValueError, match="start_date must be before end_date"):
            OptimizationConfig(
                study_name="test",
                start_date=datetime(2024, 1, 1),
                end_date=datetime(2023, 1, 1)
            )

    def test_to_snapshot(self):
        """Test conversion to snapshot dictionary."""
        config = OptimizationConfig(
            study_name="test_study",
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2024, 12, 31)
        )

        snapshot = config.to_snapshot()

        assert snapshot["study_name"] == "test_study"
        assert snapshot["objective"] == "sharpe_ratio"
        assert snapshot["n_trials"] == 100
        assert snapshot["walk_forward_mode"] == "sliding"
        assert snapshot["n_splits"] == 4
        assert snapshot["train_ratio"] == 0.75
        assert snapshot["initial_capital"] == 10000.0
        assert snapshot["symbol"] == "BTCUSDT"
        assert snapshot["timeframe"] == "15m"
        assert snapshot["start_date"] == "2023-01-01T00:00:00"
        assert snapshot["end_date"] == "2024-12-31T00:00:00"
        assert snapshot["sampler"] == "tpe"
        assert snapshot["pruner"] == "median"


class TestStudyResult:
    """Tests for StudyResult dataclass."""

    def test_create_study_result(self):
        """Test creating a study result."""
        weights_set_id = uuid4()
        run_id = uuid4()
        started_at = datetime.now()
        completed_at = datetime.now()

        result = StudyResult(
            study_name="test_study",
            run_id=run_id,
            n_trials=400,
            best_value=2.15,
            best_params={"weight_ema": 0.15, "weight_macd": 0.20},
            best_weights={"ema": 0.15, "macd": 0.20},
            weights_set_id=weights_set_id,
            started_at=started_at,
            completed_at=completed_at,
            optimization_time_seconds=3625.5
        )

        assert result.study_name == "test_study"
        assert result.run_id == run_id
        assert result.n_trials == 400
        assert result.best_value == 2.15
        assert result.best_params == {"weight_ema": 0.15, "weight_macd": 0.20}
        assert result.best_weights == {"ema": 0.15, "macd": 0.20}
        assert result.weights_set_id == weights_set_id
        assert result.started_at == started_at
        assert result.completed_at == completed_at
        assert result.optimization_time_seconds == 3625.5

    def test_to_metadata_dict(self):
        """Test conversion to metadata dictionary."""
        result = StudyResult(
            study_name="test_study",
            run_id=None,
            n_trials=400,
            best_value=2.15,
            best_params={"weight_ema": 0.15},
            best_weights={"ema": 0.15},
            weights_set_id=None,
            started_at=datetime(2024, 1, 1, 10, 0, 0),
            completed_at=datetime(2024, 1, 1, 11, 0, 0),
            optimization_time_seconds=3600.0,
            metadata={"objective": "sharpe_ratio"}
        )

        metadata = result.to_metadata_dict()

        assert metadata["study_name"] == "test_study"
        assert metadata["n_trials"] == 400
        assert metadata["n_completed"] == 400
        assert metadata["optimization_time_seconds"] == 3600.0
        assert metadata["objective"] == "sharpe_ratio"
        assert "best_trial" in metadata
        assert metadata["best_trial"]["value"] == 2.15
        assert metadata["best_trial"]["params"] == {"weight_ema": 0.15}


class TestWeightsSearchSpace:
    """Tests for WeightsSearchSpace dataclass."""

    def test_create_default_search_space(self):
        """Test creating search space with defaults."""
        search_space = WeightsSearchSpace()

        assert len(search_space.indicators) == 9
        assert "ema" in search_space.indicators
        assert "macd" in search_space.indicators
        assert "rsi" in search_space.indicators
        assert search_space.min_weight == 0.0
        assert search_space.max_weight == 1.0
        assert search_space.normalize is True

    def test_create_custom_search_space(self):
        """Test creating search space with custom values."""
        search_space = WeightsSearchSpace(
            indicators=["ema", "macd", "rsi"],
            min_weight=0.1,
            max_weight=0.5,
            normalize=False
        )

        assert search_space.indicators == ["ema", "macd", "rsi"]
        assert search_space.min_weight == 0.1
        assert search_space.max_weight == 0.5
        assert search_space.normalize is False

    def test_invalid_empty_indicators(self):
        """Test validation fails for empty indicators list."""
        with pytest.raises(ValueError, match="indicators list cannot be empty"):
            WeightsSearchSpace(indicators=[])

    def test_invalid_negative_min_weight(self):
        """Test validation fails for negative min_weight."""
        with pytest.raises(ValueError, match="min_weight must be non-negative"):
            WeightsSearchSpace(min_weight=-0.1)

    def test_invalid_max_weight(self):
        """Test validation fails for max_weight <= min_weight."""
        with pytest.raises(ValueError, match="max_weight must be greater than min_weight"):
            WeightsSearchSpace(min_weight=0.5, max_weight=0.5)

        with pytest.raises(ValueError, match="max_weight must be greater than min_weight"):
            WeightsSearchSpace(min_weight=0.6, max_weight=0.5)


class _FakeTrial:
    """Minimal Optuna-trial stand-in that records params and user attrs."""

    def __init__(self, values: dict):
        # values: prefixed param name -> value to return for that param
        self._values = values
        self.params: dict = {}
        self.user_attrs: dict = {}

    def suggest_float(self, name, low, high):
        value = self._values[name]
        self.params[name] = value
        return value

    def set_user_attr(self, key, value):
        self.user_attrs[key] = value


class TestWeightsSearchSpaceWeights:
    """Tests for weight resolution (regression: walk-forward test scores all 0.0)."""

    def test_suggest_weights_records_unprefixed_normalized_weights(self):
        """suggest_weights must record the exact backtester weights on the trial."""
        search_space = WeightsSearchSpace(
            indicators=["ema", "macd", "user_indicator"],
            fixed_weights={"user_indicator": 0.05},
        )
        trial = _FakeTrial({"weight_ema": 0.6, "weight_macd": 0.4})

        weights = search_space.suggest_weights(trial)

        # Optuna params are prefixed; only optimizable indicators are suggested.
        assert set(trial.params) == {"weight_ema", "weight_macd"}
        # Backtester weights are unprefixed and include the fixed indicator.
        assert set(weights) == {"ema", "macd", "user_indicator"}
        # Normalized to sum ~1.0.
        assert pytest.approx(sum(weights.values()), abs=1e-9) == 1.0
        # The exact same dict is recorded for the runner to reuse.
        assert trial.user_attrs["weights"] == weights

    def test_weights_from_params_matches_suggest_weights(self):
        """Reconstruction from prefixed best_params must equal the live weights."""
        search_space = WeightsSearchSpace(
            indicators=["ema", "macd", "user_indicator"],
            fixed_weights={"user_indicator": 0.05},
        )
        trial = _FakeTrial({"weight_ema": 0.6, "weight_macd": 0.4})
        live = search_space.suggest_weights(trial)

        reconstructed = search_space.weights_from_params(trial.params)

        assert reconstructed == live

    def test_weights_from_params_strips_prefix_and_excludes_defaults(self):
        """Keys are unprefixed; backtester gets recognised indicator keys, not weight_*."""
        search_space = WeightsSearchSpace(
            indicators=["ema", "macd", "rsi", "user_indicator"],
            fixed_weights={"user_indicator": 0.05},
        )
        best_params = {"weight_ema": 0.5, "weight_macd": 0.3, "weight_rsi": 0.2}

        weights = search_space.weights_from_params(best_params)

        assert not any(k.startswith("weight_") for k in weights)
        assert {"ema", "macd", "rsi", "user_indicator"} == set(weights)
