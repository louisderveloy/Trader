"""
Unit tests for optimization configuration.

This module tests configuration loading, validation, and management functions.
"""

import pytest
from decimal import Decimal
from datetime import datetime

from optimization.config import (
    create_default_config,
    validate_config,
    create_search_space
)
from optimization.types import OptimizationObjective, WalkForwardMode


class TestCreateDefaultConfig:
    """Tests for create_default_config function."""

    def test_creates_valid_config(self):
        """Test that create_default_config creates a valid configuration."""
        config = create_default_config("test_study")

        assert config.study_name == "test_study"
        assert config.objective == OptimizationObjective.SHARPE_RATIO
        assert config.n_trials == 100
        assert config.walk_forward_mode == WalkForwardMode.SLIDING
        assert config.n_splits == 4
        assert config.train_ratio == 0.75
        assert config.initial_capital == Decimal("10000.0")
        assert config.symbol == "BTCUSDT"
        assert config.timeframe == "15m"

    def test_with_custom_symbol(self):
        """Test creating config with custom symbol."""
        config = create_default_config("test_study", symbol="ETHUSDT")

        assert config.symbol == "ETHUSDT"

    def test_with_custom_timeframe(self):
        """Test creating config with custom timeframe."""
        config = create_default_config("test_study", timeframe="1h")

        assert config.timeframe == "1h"

    def test_with_date_range(self):
        """Test creating config with date range."""
        start = datetime(2023, 1, 1)
        end = datetime(2024, 12, 31)

        config = create_default_config("test_study", start_date=start, end_date=end)

        assert config.start_date == start
        assert config.end_date == end


class TestValidateConfig:
    """Tests for validate_config function."""

    def test_validates_normal_config(self):
        """Test that validate_config passes for normal configuration."""
        config = create_default_config("test_study")

        # Should not raise
        validate_config(config)

    def test_warns_on_low_trials(self):
        """Test warning when n_trials is too low."""
        config = create_default_config("test_study")
        config.n_trials = 10

        # Should not raise, but would log warning
        validate_config(config)

    def test_warns_on_low_splits(self):
        """Test warning when n_splits is too low."""
        config = create_default_config("test_study")
        config.n_splits = 1

        # Should not raise, but would log warning
        validate_config(config)

    def test_warns_on_extreme_train_ratio(self):
        """Test warning on extreme train ratios."""
        config = create_default_config("test_study")

        config.train_ratio = 0.5
        validate_config(config)  # Should warn (low)

        config.train_ratio = 0.95
        validate_config(config)  # Should warn (high)


class TestCreateSearchSpace:
    """Tests for create_search_space function."""

    def test_creates_default_search_space(self):
        """Test creating search space with defaults."""
        search_space = create_search_space()

        assert len(search_space.indicators) == 9
        assert "ema" in search_space.indicators
        assert "macd" in search_space.indicators
        assert search_space.min_weight == 0.0
        assert search_space.max_weight == 1.0
        assert search_space.normalize is True

    def test_creates_custom_search_space(self):
        """Test creating search space with custom parameters."""
        indicators = ["ema", "macd", "rsi"]
        search_space = create_search_space(
            indicators=indicators,
            min_weight=0.1,
            max_weight=0.5,
            normalize=False
        )

        assert search_space.indicators == indicators
        assert search_space.min_weight == 0.1
        assert search_space.max_weight == 0.5
        assert search_space.normalize is False
