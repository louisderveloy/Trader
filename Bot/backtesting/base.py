"""
Abstract base class for backtesting engines.

Defines the common interface that both vectorbt and event-driven
backtesting implementations must follow.
"""

from abc import ABC, abstractmethod
from typing import Optional
import asyncpg

from .types import BacktestConfig, BacktestResult


class BacktesterBase(ABC):
    """
    Abstract base class for backtesting engines.

    Both vectorbt and event-driven backtesting engines inherit from this
    class and implement the run() method according to their specific logic.

    The interface ensures both engines:
    1. Accept the same BacktestConfig
    2. Return standardized BacktestResult
    3. Calculate the same metrics for coherence validation
    """

    def __init__(
        self,
        config: BacktestConfig,
        db_pool: Optional[asyncpg.Pool] = None
    ):
        """
        Initialize backtester.

        Args:
            config: Backtesting configuration
            db_pool: Optional database connection pool for loading historical data
        """
        self.config = config
        self.db_pool = db_pool

    @abstractmethod
    async def run(self) -> BacktestResult:
        """
        Execute the backtest.

        This method must be implemented by subclasses to perform the actual
        backtesting logic (vectorized or event-driven).

        Returns:
            BacktestResult: Complete backtest result with trades and metrics

        Raises:
            Exception: If backtest fails for any reason
        """
        pass

    async def validate_config(self) -> bool:
        """
        Validate backtest configuration.

        Checks that all required parameters are present and valid.

        Returns:
            bool: True if configuration is valid

        Raises:
            ValueError: If configuration is invalid
        """
        if self.config.start_date >= self.config.end_date:
            raise ValueError("start_date must be before end_date")

        if self.config.initial_capital <= 0:
            raise ValueError("initial_capital must be positive")

        if self.config.commission_rate < 0:
            raise ValueError("commission_rate cannot be negative")

        if self.config.slippage_pct < 0:
            raise ValueError("slippage_pct cannot be negative")

        return True

    async def load_candles(self):
        """
        Load historical candle data from database.

        Subclasses can override this method to customize data loading.
        Default implementation loads from the candles table.

        Returns:
            DataFrame or list of candles depending on implementation

        Raises:
            Exception: If data loading fails
        """
        if not self.db_pool:
            raise ValueError("Database pool required to load candles")

        # This will be implemented by subclasses with their specific data format
        raise NotImplementedError("Subclasses must implement load_candles()")
