"""
Risk management module.

This module implements risk management quotas and constraints:
1. Max trades per day quota
2. Max exposure percentage limit
3. Cooldown period after trade close

Integrates with database to track daily trades and current exposure.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from .types import RiskState
from .config import RiskConfig, CooldownConfig

# Structured logging
logger = logging.getLogger(__name__)


class RiskManager:
    """
    Risk manager for enforcing quotas and exposure limits.

    This class tracks risk state and validates new positions against
    configured constraints. It queries the database for current state
    (daily trades, open positions) and maintains a local cache.
    """

    def __init__(
        self,
        run_id: int,
        risk_config: RiskConfig,
        cooldown_config: CooldownConfig,
        db_pool
    ):
        """
        Initialize risk manager.

        Args:
            run_id: Current run ID (integer)
            risk_config: Risk management configuration
            cooldown_config: Cooldown configuration
            db_pool: asyncpg connection pool for database queries
        """
        self.run_id = run_id
        self.risk_config = risk_config
        self.cooldown_config = cooldown_config
        self.db_pool = db_pool

        # Cached state (refreshed from DB)
        self._state: Optional[RiskState] = None
        self._last_refresh: Optional[datetime] = None

    async def refresh_state(self) -> RiskState:
        """
        Refresh risk state from database.

        Queries the database for:
        - Number of trades today (from trades table)
        - Last trade closed timestamp (for cooldown)
        - Current exposure (sum of open positions from orders/trades)

        Returns:
            Updated RiskState

        Raises:
            Exception: If database query fails
        """
        now = datetime.now(timezone.utc)

        async with self.db_pool.acquire() as conn:
            # Count trades today
            trades_today = await self._count_trades_today(conn, now)

            # Get last trade closed timestamp
            last_trade_closed_at = await self._get_last_trade_closed_at(conn)

            # Calculate current exposure
            current_exposure_usdt = await self._calculate_current_exposure(conn)

        self._state = RiskState(
            trades_today=trades_today,
            last_trade_closed_at=last_trade_closed_at,
            current_exposure_usdt=current_exposure_usdt
        )
        self._last_refresh = now

        logger.info(
            "Risk state refreshed",
            extra={
                "run_id": str(self.run_id),
                "trades_today": trades_today,
                "last_trade_closed_at": last_trade_closed_at.isoformat() if last_trade_closed_at else None,
                "current_exposure_usdt": float(current_exposure_usdt)
            }
        )

        return self._state

    async def _count_trades_today(self, conn, current_time: datetime) -> int:
        """
        Count trades opened today for this run.

        Args:
            conn: Database connection
            current_time: Current timestamp

        Returns:
            Number of trades today
        """
        # Start of today in UTC
        today_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)

        query = """
            SELECT COUNT(*)
            FROM trades
            WHERE run_id = $1
              AND opened_at >= $2
        """
        result = await conn.fetchval(query, self.run_id, today_start)
        return result or 0

    async def _get_last_trade_closed_at(self, conn) -> Optional[datetime]:
        """
        Get timestamp of last closed trade for this run.

        Args:
            conn: Database connection

        Returns:
            Timestamp of last closed trade, or None if no trades
        """
        query = """
            SELECT closed_at
            FROM trades
            WHERE run_id = $1
            ORDER BY closed_at DESC
            LIMIT 1
        """
        result = await conn.fetchval(query, self.run_id)
        return result

    async def _calculate_current_exposure(self, conn) -> Decimal:
        """
        Calculate current exposure from open positions.

        Sums the USDT value of all open positions (entry_price × quantity)
        for positions that are not yet closed.

        Args:
            conn: Database connection

        Returns:
            Total exposure in USDT
        """
        # Query trades that are still open (no exit_order_id yet)
        # In Phase 4, we don't have position tracking yet, so this will return 0
        # TODO: Implement proper position tracking in later phases
        query = """
            SELECT COALESCE(SUM(entry_price * quantity), 0)
            FROM trades
            WHERE run_id = $1
              AND exit_order_id IS NULL
        """
        result = await conn.fetchval(query, self.run_id)
        return Decimal(str(result)) if result else Decimal("0")

    async def can_open_new_trade(
        self,
        new_position_size_usdt: Decimal,
        total_capital: Decimal,
        current_time: Optional[datetime] = None
    ) -> tuple[bool, str]:
        """
        Check if a new trade can be opened given risk constraints.

        Validates against:
        1. Daily trade quota
        2. Cooldown period
        3. Maximum exposure limit

        Args:
            new_position_size_usdt: Size of the proposed new position in USDT
            total_capital: Total available capital in USDT
            current_time: Current timestamp (defaults to now)

        Returns:
            (can_open, reason) tuple
            - can_open: True if trade can be opened, False otherwise
            - reason: Human-readable explanation

        Example:
            >>> manager = RiskManager(run_id, risk_config, cooldown_config, db_pool)
            >>> await manager.refresh_state()
            >>> can_open, reason = await manager.can_open_new_trade(
            ...     new_position_size_usdt=Decimal("1000"),
            ...     total_capital=Decimal("10000")
            ... )
            >>> if can_open:
            ...     # Execute trade
            ... else:
            ...     print(f"Trade blocked: {reason}")
        """
        if current_time is None:
            current_time = datetime.now(timezone.utc)

        # Refresh state if stale (> 1 minute old)
        if self._state is None or (
            self._last_refresh is not None
            and (current_time - self._last_refresh).total_seconds() > 60
        ):
            await self.refresh_state()

        # Use RiskState.can_open_new_trade() for validation
        can_open, reason = self._state.can_open_new_trade(
            max_trades_per_day=self.risk_config.max_trades_per_day,
            max_exposure_percent=self.risk_config.max_exposure_percent,
            total_capital=total_capital,
            new_position_size=new_position_size_usdt,
            cooldown_seconds=self.cooldown_config.after_trade_seconds,
            current_time=current_time
        )

        logger.info(
            "Risk check performed",
            extra={
                "run_id": str(self.run_id),
                "can_open": can_open,
                "reason": reason,
                "new_position_size_usdt": float(new_position_size_usdt),
                "total_capital": float(total_capital),
                "trades_today": self._state.trades_today,
                "max_trades_per_day": self.risk_config.max_trades_per_day,
                "current_exposure_usdt": float(self._state.current_exposure_usdt),
                "max_exposure_percent": self.risk_config.max_exposure_percent
            }
        )

        return can_open, reason

    async def record_trade_opened(self):
        """
        Record that a trade was opened.

        Increments the daily trade count in local state.
        The database will be updated when the trade is actually saved.
        """
        if self._state is not None:
            self._state.trades_today += 1

        logger.info(
            "Trade opened recorded",
            extra={
                "run_id": str(self.run_id),
                "trades_today": self._state.trades_today if self._state else None
            }
        )

    async def record_trade_closed(self, closed_at: datetime):
        """
        Record that a trade was closed.

        Updates the last trade closed timestamp for cooldown tracking.

        Args:
            closed_at: Timestamp when trade was closed
        """
        if self._state is not None:
            self._state.last_trade_closed_at = closed_at

        logger.info(
            "Trade closed recorded",
            extra={
                "run_id": str(self.run_id),
                "closed_at": closed_at.isoformat()
            }
        )

    def get_state(self) -> Optional[RiskState]:
        """
        Get current risk state (may be stale).

        For real-time checks, use can_open_new_trade() which auto-refreshes.

        Returns:
            Current RiskState or None if not yet initialized
        """
        return self._state

    async def get_risk_metrics(self) -> dict:
        """
        Get current risk metrics for monitoring/dashboard.

        Returns:
            Dictionary with risk metrics
        """
        await self.refresh_state()

        return {
            "trades_today": self._state.trades_today,
            "max_trades_per_day": self.risk_config.max_trades_per_day,
            "trades_remaining_today": max(
                0,
                self.risk_config.max_trades_per_day - self._state.trades_today
            ),
            "current_exposure_usdt": float(self._state.current_exposure_usdt),
            "max_exposure_percent": self.risk_config.max_exposure_percent,
            "in_cooldown": self._state.is_in_cooldown(
                self.cooldown_config.after_trade_seconds,
                datetime.now(timezone.utc)
            ) if self._state.last_trade_closed_at else False,
            "last_trade_closed_at": (
                self._state.last_trade_closed_at.isoformat()
                if self._state.last_trade_closed_at
                else None
            )
        }
