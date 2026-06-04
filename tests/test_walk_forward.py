"""
Unit tests for walk-forward analysis.

This module tests the walk-forward split generation logic.
"""

import pytest
from datetime import datetime, timedelta

from optimization.walk_forward import generate_splits
from optimization.types import WalkForwardMode


class TestGenerateSplits:
    """Tests for generate_splits function."""

    def test_sliding_window_4_splits(self):
        """Test sliding window with 4 splits."""
        start_date = datetime(2023, 1, 1)
        end_date = datetime(2024, 1, 1)  # 1 year
        n_splits = 4
        train_ratio = 0.75

        splits = generate_splits(
            start_date, end_date, n_splits, train_ratio, WalkForwardMode.SLIDING
        )

        assert len(splits) == 4

        # Check first split
        assert splits[0].split_index == 0
        assert splits[0].train_start == start_date

        # Check last split
        assert splits[-1].split_index == 3

        # Verify no gaps between splits
        for i in range(len(splits) - 1):
            # Each split's test period should be before the next split's train period
            # (with some overlap possible in sliding window)
            assert splits[i].train_end <= splits[i + 1].train_end

    def test_expanding_window_4_splits(self):
        """Test expanding window with 4 splits."""
        start_date = datetime(2023, 1, 1)
        end_date = datetime(2024, 1, 1)
        n_splits = 4
        train_ratio = 0.75

        splits = generate_splits(
            start_date, end_date, n_splits, train_ratio, WalkForwardMode.EXPANDING
        )

        assert len(splits) == 4

        # In expanding mode, all training periods start from the beginning
        for split in splits:
            assert split.train_start == start_date

        # Training periods should grow
        for i in range(len(splits) - 1):
            assert splits[i].train_end < splits[i + 1].train_end

    def test_invalid_n_splits(self):
        """Test validation for invalid n_splits."""
        start_date = datetime(2023, 1, 1)
        end_date = datetime(2024, 1, 1)

        with pytest.raises(ValueError, match="n_splits must be at least 1"):
            generate_splits(start_date, end_date, 0, 0.75, WalkForwardMode.SLIDING)

    def test_invalid_train_ratio(self):
        """Test validation for invalid train_ratio."""
        start_date = datetime(2023, 1, 1)
        end_date = datetime(2024, 1, 1)

        with pytest.raises(ValueError, match="train_ratio must be in \\(0, 1\\)"):
            generate_splits(start_date, end_date, 4, 0.0, WalkForwardMode.SLIDING)

        with pytest.raises(ValueError, match="train_ratio must be in \\(0, 1\\)"):
            generate_splits(start_date, end_date, 4, 1.0, WalkForwardMode.SLIDING)

    def test_invalid_date_order(self):
        """Test validation for invalid date order."""
        start_date = datetime(2024, 1, 1)
        end_date = datetime(2023, 1, 1)  # Before start

        with pytest.raises(ValueError, match="start_date must be before end_date"):
            generate_splits(start_date, end_date, 4, 0.75, WalkForwardMode.SLIDING)

    def test_insufficient_data(self):
        """Test validation for insufficient data."""
        start_date = datetime(2023, 1, 1)
        end_date = datetime(2023, 1, 2)  # Only 1 day
        n_splits = 10  # Too many splits

        with pytest.raises(ValueError, match="Insufficient data"):
            generate_splits(start_date, end_date, n_splits, 0.75, WalkForwardMode.SLIDING)

    def test_all_splits_have_required_fields(self):
        """Test that all splits have required fields."""
        start_date = datetime(2023, 1, 1)
        end_date = datetime(2024, 1, 1)

        splits = generate_splits(
            start_date, end_date, 4, 0.75, WalkForwardMode.SLIDING
        )

        for split in splits:
            assert isinstance(split.split_index, int)
            assert isinstance(split.train_start, datetime)
            assert isinstance(split.train_end, datetime)
            assert isinstance(split.test_start, datetime)
            assert isinstance(split.test_end, datetime)
            assert split.train_start < split.train_end
            assert split.test_start < split.test_end
            assert split.train_end <= split.test_start

    def test_different_train_ratios(self):
        """Test split generation with different train ratios."""
        start_date = datetime(2023, 1, 1)
        end_date = datetime(2024, 1, 1)

        # High train ratio (more training data)
        splits_high = generate_splits(
            start_date, end_date, 4, 0.9, WalkForwardMode.SLIDING
        )

        # Low train ratio (more testing data)
        splits_low = generate_splits(
            start_date, end_date, 4, 0.6, WalkForwardMode.SLIDING
        )

        # With higher train ratio, training periods should be longer
        train_duration_high = splits_high[0].train_end - splits_high[0].train_start
        train_duration_low = splits_low[0].train_end - splits_low[0].train_start

        assert train_duration_high > train_duration_low
