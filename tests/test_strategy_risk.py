"""
Unit tests for strategy/risk.py

Tests RiskManager with database mocking.
"""

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from strategy.risk import RiskManager
from strategy.config import RiskConfig, CooldownConfig
from strategy.types import RiskState


# Fixtures

@pytest.fixture
def run_id():
    """Generate a test run ID"""
    return uuid4()


@pytest.fixture
def risk_config():
    """Create a test risk configuration"""
    return RiskConfig(
        max_trades_per_day=5,
        max_exposure_percent=30.0
    )


@pytest.fixture
def cooldown_config():
    """Create a test cooldown configuration"""
    return CooldownConfig(after_trade_seconds=3600)


@pytest.fixture
def mock_db_pool():
    """Create a mock database pool"""
    pool = MagicMock()
    return pool


@pytest.fixture
def risk_manager(run_id, risk_config, cooldown_config, mock_db_pool):
    """Create a RiskManager instance with mocked DB"""
    return RiskManager(
        run_id=run_id,
        risk_config=risk_config,
        cooldown_config=cooldown_config,
        db_pool=mock_db_pool
    )


# --- RiskManager initialization tests ---

def test_risk_manager_initialization(run_id, risk_config, cooldown_config, mock_db_pool):
    """Test RiskManager initialization"""
    manager = RiskManager(
        run_id=run_id,
        risk_config=risk_config,
        cooldown_config=cooldown_config,
        db_pool=mock_db_pool
    )

    assert manager.run_id == run_id
    assert manager.risk_config == risk_config
    assert manager.cooldown_config == cooldown_config
    assert manager.db_pool == mock_db_pool
    assert manager._state is None


# --- refresh_state tests ---

@pytest.mark.asyncio
async def test_refresh_state_no_trades(risk_manager, mock_db_pool):
    """Test refresh_state when no trades exist"""
    # Mock database connection and queries
    mock_conn = AsyncMock()
    mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

    # Mock query results: no trades
    mock_conn.fetchval.side_effect = [
        0,  # trades_today count
        None,  # last_trade_closed_at
        Decimal("0")  # current_exposure
    ]

    state = await risk_manager.refresh_state()

    assert state.trades_today == 0
    assert state.last_trade_closed_at is None
    assert state.current_exposure_usdt == Decimal("0")


@pytest.mark.asyncio
async def test_refresh_state_with_trades(risk_manager, mock_db_pool):
    """Test refresh_state with existing trades"""
    now = datetime.now(timezone.utc)
    last_trade_time = now - timedelta(hours=2)

    mock_conn = AsyncMock()
    mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

    # Mock query results: 3 trades today, last closed 2h ago, $2000 exposure
    mock_conn.fetchval.side_effect = [
        3,  # trades_today
        last_trade_time,  # last_trade_closed_at
        Decimal("2000")  # current_exposure
    ]

    state = await risk_manager.refresh_state()

    assert state.trades_today == 3
    assert state.last_trade_closed_at == last_trade_time
    assert state.current_exposure_usdt == Decimal("2000")


@pytest.mark.asyncio
async def test_refresh_state_caches_result(risk_manager, mock_db_pool):
    """Test that refresh_state caches the result"""
    mock_conn = AsyncMock()
    mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

    mock_conn.fetchval.side_effect = [0, None, Decimal("0")]

    await risk_manager.refresh_state()

    # State should be cached
    assert risk_manager._state is not None
    assert risk_manager._last_refresh is not None


# --- _count_trades_today tests ---

@pytest.mark.asyncio
async def test_count_trades_today_zero(risk_manager, mock_db_pool):
    """Test counting trades when none exist today"""
    now = datetime.now(timezone.utc)

    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = 0

    count = await risk_manager._count_trades_today(mock_conn, now)

    assert count == 0
    # Verify query was called with correct parameters
    mock_conn.fetchval.assert_called_once()


@pytest.mark.asyncio
async def test_count_trades_today_multiple(risk_manager, mock_db_pool):
    """Test counting multiple trades today"""
    now = datetime.now(timezone.utc)

    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = 5

    count = await risk_manager._count_trades_today(mock_conn, now)

    assert count == 5


# --- _get_last_trade_closed_at tests ---

@pytest.mark.asyncio
async def test_get_last_trade_closed_at_none(risk_manager):
    """Test getting last trade time when no trades exist"""
    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = None

    result = await risk_manager._get_last_trade_closed_at(mock_conn)

    assert result is None


@pytest.mark.asyncio
async def test_get_last_trade_closed_at_exists(risk_manager):
    """Test getting last trade time when trades exist"""
    last_time = datetime.now(timezone.utc) - timedelta(hours=1)

    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = last_time

    result = await risk_manager._get_last_trade_closed_at(mock_conn)

    assert result == last_time


# --- _calculate_current_exposure tests ---

@pytest.mark.asyncio
async def test_calculate_current_exposure_zero(risk_manager):
    """Test calculating exposure when no positions open"""
    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = Decimal("0")

    exposure = await risk_manager._calculate_current_exposure(mock_conn)

    assert exposure == Decimal("0")


@pytest.mark.asyncio
async def test_calculate_current_exposure_with_positions(risk_manager):
    """Test calculating exposure with open positions"""
    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = Decimal("2500")

    exposure = await risk_manager._calculate_current_exposure(mock_conn)

    assert exposure == Decimal("2500")


# --- can_open_new_trade tests ---

@pytest.mark.asyncio
async def test_can_open_new_trade_ok(risk_manager, mock_db_pool):
    """Test can_open_new_trade when all checks pass"""
    now = datetime.now(timezone.utc)

    # Setup state: 2 trades, last trade 2h ago, $1000 exposure
    mock_conn = AsyncMock()
    mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

    mock_conn.fetchval.side_effect = [
        2,  # trades_today
        now - timedelta(hours=2),  # last_trade_closed_at
        Decimal("1000")  # current_exposure
    ]

    can_open, reason = await risk_manager.can_open_new_trade(
        new_position_size_usdt=Decimal("1000"),
        total_capital=Decimal("10000"),
        current_time=now
    )

    assert can_open is True
    assert reason == "OK"


@pytest.mark.asyncio
async def test_can_open_new_trade_quota_exceeded(risk_manager, mock_db_pool):
    """Test can_open_new_trade when daily quota is exceeded"""
    now = datetime.now(timezone.utc)

    # Setup state: 5 trades (at max), last trade 2h ago, $1000 exposure
    mock_conn = AsyncMock()
    mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

    mock_conn.fetchval.side_effect = [
        5,  # trades_today (max is 5)
        now - timedelta(hours=2),
        Decimal("1000")
    ]

    can_open, reason = await risk_manager.can_open_new_trade(
        new_position_size_usdt=Decimal("1000"),
        total_capital=Decimal("10000"),
        current_time=now
    )

    assert can_open is False
    assert "quota" in reason.lower()


@pytest.mark.asyncio
async def test_can_open_new_trade_in_cooldown(risk_manager, mock_db_pool):
    """Test can_open_new_trade when in cooldown period"""
    now = datetime.now(timezone.utc)

    # Setup state: 2 trades, last trade 30 min ago (cooldown is 1h)
    mock_conn = AsyncMock()
    mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

    mock_conn.fetchval.side_effect = [
        2,
        now - timedelta(minutes=30),  # Still in cooldown
        Decimal("1000")
    ]

    can_open, reason = await risk_manager.can_open_new_trade(
        new_position_size_usdt=Decimal("1000"),
        total_capital=Decimal("10000"),
        current_time=now
    )

    assert can_open is False
    assert "cooldown" in reason.lower()


@pytest.mark.asyncio
async def test_can_open_new_trade_exposure_exceeded(risk_manager, mock_db_pool):
    """Test can_open_new_trade when exposure limit would be exceeded"""
    now = datetime.now(timezone.utc)

    # Setup state: 2 trades, last trade 2h ago, $2500 exposure (max is 30% = $3000)
    mock_conn = AsyncMock()
    mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

    mock_conn.fetchval.side_effect = [
        2,
        now - timedelta(hours=2),
        Decimal("2500")  # Already at $2500
    ]

    can_open, reason = await risk_manager.can_open_new_trade(
        new_position_size_usdt=Decimal("1000"),  # Would make $3500 > $3000 limit
        total_capital=Decimal("10000"),
        current_time=now
    )

    assert can_open is False
    assert "exposure" in reason.lower()


@pytest.mark.asyncio
async def test_can_open_new_trade_refreshes_stale_state(risk_manager, mock_db_pool):
    """Test that can_open_new_trade refreshes stale state"""
    now = datetime.now(timezone.utc)

    # First refresh
    mock_conn = AsyncMock()
    mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn
    mock_conn.fetchval.side_effect = [0, None, Decimal("0")]

    await risk_manager.refresh_state()

    # Set last refresh to > 1 minute ago (stale)
    risk_manager._last_refresh = now - timedelta(minutes=2)

    # Reset mock for second refresh
    mock_conn.fetchval.side_effect = [1, None, Decimal("0")]

    await risk_manager.can_open_new_trade(
        new_position_size_usdt=Decimal("1000"),
        total_capital=Decimal("10000"),
        current_time=now
    )

    # Should have refreshed state (called fetchval multiple times)
    assert mock_conn.fetchval.call_count >= 3


# --- record_trade_opened tests ---

@pytest.mark.asyncio
async def test_record_trade_opened(risk_manager, mock_db_pool):
    """Test recording a trade opened"""
    # Initialize state first
    mock_conn = AsyncMock()
    mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn
    mock_conn.fetchval.side_effect = [2, None, Decimal("1000")]

    await risk_manager.refresh_state()

    initial_count = risk_manager._state.trades_today

    await risk_manager.record_trade_opened()

    assert risk_manager._state.trades_today == initial_count + 1


@pytest.mark.asyncio
async def test_record_trade_opened_no_state(risk_manager):
    """Test recording trade opened when state is None"""
    # Should not raise error
    await risk_manager.record_trade_opened()


# --- record_trade_closed tests ---

@pytest.mark.asyncio
async def test_record_trade_closed(risk_manager, mock_db_pool):
    """Test recording a trade closed"""
    now = datetime.now(timezone.utc)

    # Initialize state first
    mock_conn = AsyncMock()
    mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn
    mock_conn.fetchval.side_effect = [2, None, Decimal("1000")]

    await risk_manager.refresh_state()

    await risk_manager.record_trade_closed(now)

    assert risk_manager._state.last_trade_closed_at == now


@pytest.mark.asyncio
async def test_record_trade_closed_no_state(risk_manager):
    """Test recording trade closed when state is None"""
    now = datetime.now(timezone.utc)

    # Should not raise error
    await risk_manager.record_trade_closed(now)


# --- get_state tests ---

def test_get_state_none(risk_manager):
    """Test get_state when not initialized"""
    state = risk_manager.get_state()

    assert state is None


@pytest.mark.asyncio
async def test_get_state_initialized(risk_manager, mock_db_pool):
    """Test get_state after initialization"""
    mock_conn = AsyncMock()
    mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn
    mock_conn.fetchval.side_effect = [2, None, Decimal("1000")]

    await risk_manager.refresh_state()

    state = risk_manager.get_state()

    assert state is not None
    assert state.trades_today == 2


# --- get_risk_metrics tests ---

@pytest.mark.asyncio
async def test_get_risk_metrics(risk_manager, mock_db_pool):
    """Test getting risk metrics for dashboard"""
    now = datetime.now(timezone.utc)

    mock_conn = AsyncMock()
    mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

    mock_conn.fetchval.side_effect = [
        3,  # trades_today
        now - timedelta(hours=2),  # last_trade_closed_at (not in cooldown)
        Decimal("2000")  # current_exposure
    ]

    metrics = await risk_manager.get_risk_metrics()

    assert metrics["trades_today"] == 3
    assert metrics["max_trades_per_day"] == 5
    assert metrics["trades_remaining_today"] == 2
    assert metrics["current_exposure_usdt"] == 2000.0
    assert metrics["max_exposure_percent"] == 30.0
    assert metrics["in_cooldown"] is False
    assert metrics["last_trade_closed_at"] is not None


@pytest.mark.asyncio
async def test_get_risk_metrics_in_cooldown(risk_manager, mock_db_pool):
    """Test risk metrics when in cooldown"""
    now = datetime.now(timezone.utc)

    mock_conn = AsyncMock()
    mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

    mock_conn.fetchval.side_effect = [
        2,
        now - timedelta(minutes=30),  # 30 min ago (in cooldown)
        Decimal("1000")
    ]

    metrics = await risk_manager.get_risk_metrics()

    assert metrics["in_cooldown"] is True


@pytest.mark.asyncio
async def test_get_risk_metrics_no_trades(risk_manager, mock_db_pool):
    """Test risk metrics when no trades exist"""
    mock_conn = AsyncMock()
    mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn

    mock_conn.fetchval.side_effect = [0, None, Decimal("0")]

    metrics = await risk_manager.get_risk_metrics()

    assert metrics["trades_today"] == 0
    assert metrics["trades_remaining_today"] == 5
    assert metrics["in_cooldown"] is False
    assert metrics["last_trade_closed_at"] is None
