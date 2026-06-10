"""
Request/response models for starting and controlling runs.

``StartRunRequest`` is the security-critical boundary: every field that ends up
as a CLI argument for the spawned bot process is validated here against a strict
allowlist *before* it reaches the database command channel or the supervisor
(security review Finding #1 / #16). Values are normalised (dates re-serialised to
ISO, symbol upper-cased) so raw client strings never flow into an argv array.
"""

import secrets
from datetime import date
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from ..config import settings

# --- Allowlists -------------------------------------------------------------

ALLOWED_TIMEFRAMES = {
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h", "1d",
}

# Phrase the operator must type to start a real-money (mainnet) live run.
MAINNET_CONFIRM_PHRASE = "I UNDERSTAND"

# Backtest starting capital must be a positive integer below the signed 32-bit
# maximum (0 < x < 2^31 - 1).
MAX_INITIAL_CAPITAL = 2_147_483_647


class RunTypeStart(str, Enum):
    """Run types startable from the dashboard (optimization is excluded by design)."""

    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"


class BacktestEngine(str, Enum):
    """Backtesting engine selection."""

    VECTORBT = "vectorbt"
    EVENT_DRIVEN = "event_driven"


class StartRunRequest(BaseModel):
    """Validated request to start a run.

    Unknown fields are rejected (``extra='forbid'``) so a typo or an injected
    flag-like key cannot slip through unnoticed.
    """

    model_config = {"extra": "forbid"}

    run_type: RunTypeStart = Field(..., description="backtest, paper or live")
    symbol: str = Field(default=settings.binance_default_symbol, description="Trading pair (USDC quote)")
    timeframe: str = Field(default=settings.binance_default_timeframe, description="Candle timeframe")

    # Backtest-only
    start_date: Optional[date] = Field(default=None, description="Backtest start date (ISO)")
    end_date: Optional[date] = Field(default=None, description="Backtest end date (ISO)")
    initial_capital: Optional[int] = Field(default=None, description="Backtest starting capital (USDC), positive integer")
    weights_set_id: Optional[UUID] = Field(default=None, description="Weights set to use (active set if null)")
    engine: Optional[BacktestEngine] = Field(default=None, description="Backtest engine")
    save: bool = Field(default=True, description="Persist backtest results to the run record")

    # Live-only
    testnet: Optional[bool] = Field(default=None, description="Live: true=testnet, false=mainnet (required for live)")
    confirm_phrase: Optional[str] = Field(default=None, description="Mainnet safety phrase ('I UNDERSTAND')")

    # --- field validators ---------------------------------------------------

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, v: str) -> str:
        v = v.strip().upper()
        allowed = settings.available_symbols_list
        if v not in allowed:
            raise ValueError(f"symbol must be one of {allowed}")
        return v

    @field_validator("timeframe")
    @classmethod
    def _validate_timeframe(cls, v: str) -> str:
        v = v.strip()
        if v not in ALLOWED_TIMEFRAMES:
            raise ValueError(f"timeframe must be one of {sorted(ALLOWED_TIMEFRAMES)}")
        return v

    @field_validator("initial_capital")
    @classmethod
    def _validate_capital(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return v
        if not (0 < v < MAX_INITIAL_CAPITAL):
            raise ValueError(
                f"initial_capital must be a positive integer below {MAX_INITIAL_CAPITAL}"
            )
        return v

    # --- cross-field validation ---------------------------------------------

    @model_validator(mode="after")
    def _validate_by_run_type(self) -> "StartRunRequest":
        if self.run_type == RunTypeStart.BACKTEST:
            if self.start_date is None or self.end_date is None:
                raise ValueError("backtest requires start_date and end_date")
            if self.end_date <= self.start_date:
                raise ValueError("end_date must be after start_date")
            if self.engine is None:
                self.engine = BacktestEngine.VECTORBT
            if self.initial_capital is None:
                self.initial_capital = int(settings.backtest_initial_capital)
            # Live-only fields are meaningless here.
            self.testnet = None
            self.confirm_phrase = None

        elif self.run_type == RunTypeStart.PAPER:
            # Paper always runs against testnet prices; no capital/date/engine inputs.
            self.testnet = None
            self.confirm_phrase = None
            self.initial_capital = None
            self.weights_set_id = None
            self.start_date = self.end_date = None
            self.engine = None

        elif self.run_type == RunTypeStart.LIVE:
            if self.testnet is None:
                raise ValueError("live runs require an explicit 'testnet' boolean")
            # initial_capital is meaningless for live (capital comes from the account).
            if self.initial_capital is not None:
                raise ValueError("initial_capital is not allowed for live runs")
            if self.testnet is False:
                # Mainnet: require the exact safety phrase (constant-time compare).
                if self.confirm_phrase is None or not secrets.compare_digest(
                    self.confirm_phrase, MAINNET_CONFIRM_PHRASE
                ):
                    raise ValueError(
                        f"mainnet live requires confirm_phrase == '{MAINNET_CONFIRM_PHRASE}'"
                    )
            self.start_date = self.end_date = None
            self.engine = None

        return self

    # --- serialisation ------------------------------------------------------

    def to_command_params(self) -> dict[str, Any]:
        """Normalised, JSON-safe params stored in ``run_commands.params``.

        The supervisor rebuilds the argv from these (and re-validates them). The
        confirm phrase is deliberately omitted — it is a gate, not a bot input.
        """
        params: dict[str, Any] = {
            "run_type": self.run_type.value,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
        }
        if self.run_type == RunTypeStart.BACKTEST:
            params.update(
                start_date=self.start_date.isoformat() if self.start_date else None,
                end_date=self.end_date.isoformat() if self.end_date else None,
                initial_capital=self.initial_capital,
                weights_set_id=str(self.weights_set_id) if self.weights_set_id else None,
                engine=self.engine.value if self.engine else None,
                save=self.save,
            )
        elif self.run_type == RunTypeStart.LIVE:
            params.update(testnet=self.testnet)
        return params

    def environment(self) -> str:
        """Environment label for the runs row, matching the bot's conventions.

        Backtest uses ``dev`` because its adoption path goes through ``RunManager``,
        whose ``Run`` dataclass parses ``RunEnvironment`` (dev/staging/prod only) —
        this mirrors the existing CLI backtest. Paper/live write their environment
        via raw SQL and the bot overwrites it on adoption, so the richer labels are safe.
        """
        if self.run_type == RunTypeStart.BACKTEST:
            return "dev"
        if self.run_type == RunTypeStart.PAPER:
            return "paper"
        return "testnet" if self.testnet else "live"


class StartRunResponse(BaseModel):
    """Returned when a start command is accepted (run created in PENDING)."""

    run_id: int = Field(..., description="Id of the created (pending) run")
    command_id: int = Field(..., description="Id of the queued start command")
    status: str = Field(default="pending", description="Initial run status")
    message: str = Field(default="Run start command queued")


class RunCommandResponse(BaseModel):
    """Returned when a stop/kill command is accepted."""

    run_id: int = Field(..., description="Target run id")
    command_id: int = Field(..., description="Id of the queued command")
    kind: str = Field(..., description="Command kind: stop or kill")
    message: str = Field(..., description="Human-readable acknowledgement")


class RunLogsResponse(BaseModel):
    """Snapshot of the last N log lines for a run."""

    run_id: int = Field(..., description="Run id")
    lines: list[str] = Field(default_factory=list, description="Last log lines (oldest first)")
    truncated: bool = Field(default=False, description="True if older lines were dropped")
