"""
Discord notification module.

This module provides Discord webhook integration with database logging
for all notification events.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

import asyncpg
import httpx

logger = logging.getLogger(__name__)


class NotificationType(str, Enum):
    """Types of notifications."""

    TRADE_OPENED = "trade_opened"
    TRADE_CLOSED = "trade_closed"
    ORDER_FILLED = "order_filled"
    RUN_COMPLETED = "run_completed"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    OPTIMIZATION_COMPLETE = "optimization_complete"
    BOT_STARTED = "bot_started"
    BOT_STOPPED = "bot_stopped"


class DiscordNotifier:
    """
    Discord webhook notifier with rate limiting and database logging.

    This class handles sending notifications to Discord via webhooks
    and logs all notification events to the notifications_log table.

    Attributes:
        webhook_url: Discord webhook URL
        db_pool: Database connection pool
        rate_limit_seconds: Minimum seconds between notifications
        enabled: Whether notifications are enabled
    """

    def __init__(
            self,
            webhook_url: str,
            db_pool: asyncpg.Pool,
            rate_limit_seconds: int = 5,
            enabled: bool = True,
    ):
        """
        Initialize Discord notifier.

        Args:
            webhook_url: Discord webhook URL
            db_pool: Database connection pool
            rate_limit_seconds: Minimum seconds between notifications (default: 5)
            enabled: Whether notifications are enabled (default: True)
        """
        self.webhook_url = webhook_url
        self.db_pool = db_pool
        self.rate_limit_seconds = rate_limit_seconds
        self.enabled = enabled

        self._last_notification_time: Optional[datetime] = None
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def close(self):
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def send(
            self,
            message: str,
            notification_type: NotificationType,
            metadata: Optional[dict[str, Any]] = None,
    ) -> bool:
        """
        Send a Discord notification and log to database.

        Args:
            message: Message content to send
            notification_type: Type of notification
            metadata: Optional additional metadata

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            logger.debug("Notifications disabled, skipping")
            return False

        # Check rate limit
        now = datetime.now(timezone.utc)
        if self._last_notification_time:
            elapsed = (now - self._last_notification_time).total_seconds()
            if elapsed < self.rate_limit_seconds:
                wait_time = self.rate_limit_seconds - elapsed
                logger.debug(f"Rate limited, waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)

        # Send to Discord
        status = "sent"
        error_message = None

        try:
            client = await self._get_client()
            response = await client.post(
                self.webhook_url,
                json={"content": message},
            )

            if response.status_code not in (200, 204):
                status = "failed"
                error_message = f"HTTP {response.status_code}: {response.text}"
                logger.error(f"Discord notification failed: {error_message}")

        except Exception as e:
            status = "failed"
            error_message = str(e)
            logger.error(f"Discord notification error: {e}")

        self._last_notification_time = datetime.now(timezone.utc)

        # Log to database
        await self._log_notification(
            notification_type=notification_type,
            message=message,
            status=status,
            metadata={
                **(metadata or {}),
                "error": error_message,
            } if error_message else metadata,
        )

        return status == "sent"

    async def _log_notification(
            self,
            notification_type: NotificationType,
            message: str,
            status: str,
            metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Log notification to database."""
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO notifications_log (
                        notification_type, message, status, metadata, sent_at
                    )
                    VALUES ($1, $2, $3, $4, $5)
                    """,
                    notification_type.value,
                    message,
                    status,
                    json.dumps(metadata) if metadata else None,
                    datetime.now(timezone.utc),
                )
        except Exception as e:
            logger.error(f"Failed to log notification: {e}")

    async def notify_trade_opened(
            self,
            symbol: str,
            side: str,
            price: Decimal,
            quantity: Decimal,
            score: Optional[float] = None,
    ) -> bool:
        """
        Send notification for trade opened.

        Args:
            symbol: Trading symbol
            side: Trade side (long/short)
            price: Entry price
            quantity: Position quantity
            score: Optional weighted score that triggered the trade

        Returns:
            True if sent successfully
        """
        side_emoji = "🟢" if side.lower() == "long" else "🔴"
        score_str = f"\n💡 Signal: **{score:.3f}**" if score is not None else ""

        message = (
            f"{side_emoji} **{side.upper()}** POSITION OPENED\n"
            f">>> 💰 Entry: **{price:.2f}** $\n"
            f"📦 Quantity: **{quantity:.6f}**\n"
            f"🔗 {symbol}"
            f"{score_str}"
        )

        return await self.send(
            message=message,
            notification_type=NotificationType.TRADE_OPENED,
            metadata={
                "symbol": symbol,
                "side": side,
                "price": str(price),
                "quantity": str(quantity),
                "score": score,
            },
        )

    async def notify_trade_closed(
            self,
            symbol: str,
            side: str,
            entry_price: Decimal,
            exit_price: Decimal,
            pnl: Decimal,
            pnl_pct: float,
            reason: str,
    ) -> bool:
        """
        Send notification for trade closed.

        Args:
            symbol: Trading symbol
            side: Trade side (long/short)
            entry_price: Entry price
            exit_price: Exit price
            pnl: Profit/loss in USDT
            pnl_pct: Profit/loss percentage
            reason: Exit reason

        Returns:
            True if sent successfully
        """
        # Format P&L with emoji
        pnl_emoji = "🟢" if pnl >= 0 else "🔴"
        pnl_sign = "+" if pnl >= 0 else ""

        message = (
            f"**Trade Closed**\n"
            f">>> {pnl_emoji} **{pnl_sign}{pnl:.2f}** $ **({pnl_sign}{pnl_pct:.2f}%)**\n"
            f"👉 Entry: **{entry_price:.2f}** $\n"
            f"👈 Exit: **{exit_price:.2f}** $\n"
            f"🔗 {symbol}"
        )

        return await self.send(
            message=message,
            notification_type=NotificationType.TRADE_CLOSED,
            metadata={
                "symbol": symbol,
                "side": side,
                "entry_price": str(entry_price),
                "exit_price": str(exit_price),
                "pnl": str(pnl),
                "pnl_pct": pnl_pct,
                "reason": reason,
            },
        )

    async def notify_error(
            self,
            error_type: str,
            message: str,
            critical: bool = False,
    ) -> bool:
        """
        Send notification for an error.

        Args:
            error_type: Type of error
            message: Error message
            critical: Whether this is a critical error

        Returns:
            True if sent successfully
        """
        severity_emoji = "🚨" if critical else "⚠️"
        severity = "CRITICAL" if critical else "ERROR"
        notification_message = (
            f"{severity_emoji} **{severity}**\n"
            f">>> 📋 Type: {error_type}\n"
            f"💬 {message}"
        )

        return await self.send(
            message=notification_message,
            notification_type=NotificationType.ERROR,
            metadata={
                "error_type": error_type,
                "error_message": message,
                "critical": critical,
            },
        )

    async def notify_optimization_complete(
            self,
            study_name: str,
            best_value: float,
            best_params: dict[str, float],
            n_trials: int,
            duration_seconds: float,
    ) -> bool:
        """
        Send notification for optimization completion.

        Args:
            study_name: Name of the Optuna study
            best_value: Best objective value found
            best_params: Best parameters found
            n_trials: Number of trials completed
            duration_seconds: Total optimization time

        Returns:
            True if sent successfully
        """
        # Format duration
        hours = int(duration_seconds // 3600)
        minutes = int((duration_seconds % 3600) // 60)
        duration_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"

        # Format top params
        top_params = sorted(best_params.items(), key=lambda x: -x[1])[:5]
        params_str = "\n".join([f"  {k}: {v:.3f}" for k, v in top_params])

        message = (
            f"🧪 **OPTIMIZATION COMPLETE**\n"
            f">>> 📊 Best Score: **{best_value:.4f}**\n"
            f"📈 Study: {study_name}\n"
            f"🔄 Trials: **{n_trials}**\n"
            f"🏆 Top Weights:\n{params_str}"
            f"⏱️ Duration: **{duration_str}**\n"
        )

        return await self.send(
            message=message,
            notification_type=NotificationType.OPTIMIZATION_COMPLETE,
            metadata={
                "study_name": study_name,
                "best_value": str(best_value),
                "best_params": json.dumps({k: v for k, v in best_params.items()}),
                "n_trials": str(n_trials),
                "duration_seconds": str(duration_seconds),
            },
        )

    async def notify_bot_started(
            self,
            mode: str,
            symbol: str,
            testnet: bool,
    ) -> bool:
        """
        Send notification for bot startup.

        Args:
            mode: Trading mode (paper/live)
            symbol: Trading symbol
            testnet: Whether using testnet

        Returns:
            True if sent successfully
        """
        network = "TESTNET" if testnet else "MAINNET"
        network_emoji = "🧪" if testnet else "💸"
        mode_emoji = "📝" if mode.lower() == "paper" else "🎯"
        message = (
            f"🚦** BOT STARTED **🚦\n"
            f">>> 🔗 {symbol}\n"
            f"{mode_emoji} **{mode.upper()} TRADING**\n"
            f"{network_emoji} {network}"
        )

        return await self.send(
            message=message,
            notification_type=NotificationType.BOT_STARTED,
            metadata={
                "mode": mode,
                "symbol": symbol,
                "testnet": str(testnet),
            },
        )

    async def notify_bot_stopped(
            self,
            reason: str,
            trades_today: int,
            capital: Decimal,
    ) -> bool:
        """
        Send notification for bot shutdown.

        Args:
            reason: Shutdown reason
            trades_today: Number of trades executed today
            capital: Current capital

        Returns:
            True if sent successfully
        """
        message = (
            f"🛑 **BOT STOPPED**\n"
            f">>> 📌 Reason: {reason}\n"
            f"📊 Trades: **{trades_today}**\n"
            f"💰 Capital: **{capital:.2f}** $"
        )

        return await self.send(
            message=message,
            notification_type=NotificationType.BOT_STOPPED,
            metadata={
                "reason": reason,
                "trades_today": str(trades_today),
                "capital": str(capital),
            },
        )

    async def notify_order_filled(
            self,
            symbol: str,
            side: str,
            filled_price: Decimal,
            filled_quantity: Decimal,
            order_type: str,
            commission: Decimal,
            testnet: bool,
    ) -> bool:
        """
        Send notification for order filled (buy or sell).

        Args:
            symbol: Trading symbol
            side: Order side (buy/sell)
            filled_price: Filled price
            filled_quantity: Filled quantity
            order_type: Order type (limit/market)
            commission: Commission paid
            testnet: Whether on testnet

        Returns:
            True if sent successfully
        """
        network = "TESTNET" if testnet else "MAINNET"
        network_emoji = "🧪" if testnet else "💸"
        side_emoji = "🟢" if side.lower() == "buy" else "🔴"
        volume_usd = filled_price * filled_quantity

        message = (
            f"{network_emoji} **{network}** | {side_emoji} {side.upper()} ({symbol})\n"
            f">>> 💵 Volume: **${volume_usd:.2f}**\n"
            f"💰 Price: **{filled_price:.2f}** $\n"
            f"📦 Quantity: **{filled_quantity:.6f}**\n"
            f"🔗 {symbol}\n"
            f"🏧 Type: {order_type.upper()}\n"
            f"💎 Commission: {commission:.4f} $"
        )

        return await self.send(
            message=message,
            notification_type=NotificationType.ORDER_FILLED,
            metadata={
                "symbol": symbol,
                "side": side,
                "filled_price": str(filled_price),
                "filled_quantity": str(filled_quantity),
                "volume_usd": str(volume_usd),
                "order_type": order_type,
                "commission": str(commission),
                "network": network,
            },
        )

    async def notify_run_completed(
            self,
            run_type: str,
            symbol: str,
            environment: str,
            start_date: datetime,
            end_date: datetime,
            win_rate: Optional[float] = None,
            total_pnl: Optional[Decimal] = None,
    ) -> bool:
        """
        Send notification for run completion.

        Args:
            run_type: Type of run (backtest/optimization/paper/live)
            symbol: Trading symbol
            environment: Environment (dev/staging/prod)
            start_date: Run start date
            end_date: Run end date
            win_rate: Optional win rate for backtest/optimization
            total_pnl: Optional total P&L for backtest/optimization

        Returns:
            True if sent successfully
        """
        # Format P&L with emoji
        pnl_emoji = "🟢" if (total_pnl and total_pnl >= 0) else "🔴"
        pnl_sign = "+" if (total_pnl and total_pnl >= 0) else ""

        # Determine network emoji based on environment
        network_emoji = "🧪" if environment.lower() in ["dev", "staging"] else "💸"

        message = (f"**RUN COMPLETE**\n"
                   f"⚙️ Type: {run_type.upper()}\n"
                   f">>> 🔗 {symbol}\n")

        # P&L if available
        if total_pnl is not None:
            message += f"{pnl_emoji} P&L: **{pnl_sign}{total_pnl:.2f}** $\n"

        # Win rate if available
        if win_rate is not None:
            message += f"📈 Win Rate: **{win_rate:.2f}%**\n"

        message += (

            f"{network_emoji} {environment.upper()}\n"
            f"⏱️ Started: {start_date.strftime('%Y-%m-%d %H:%M UTC')}"
        )

        metadata = {
            "run_type": run_type,
            "symbol": symbol,
            "environment": environment,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }

        if win_rate is not None:
            metadata["win_rate"] = str(win_rate)

        if total_pnl is not None:
            metadata["total_pnl"] = str(total_pnl)

        return await self.send(
            message=message,
            notification_type=NotificationType.RUN_COMPLETED,
            metadata=metadata,
        )
