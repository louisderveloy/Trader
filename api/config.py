"""
API configuration loaded from environment variables.

This module uses Pydantic settings to load and validate configuration
from environment variables with type checking and defaults.
"""

from typing import Optional

from pydantic import Field, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    API configuration from environment variables.

    All settings are loaded from .env file or environment.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ==========================================
    # GENERAL
    # ==========================================
    environment: str = Field(default="dev", description="Environment: dev, staging, prod")

    # ==========================================
    # DATABASE
    # ==========================================
    postgres_host: str = Field(default="postgres", description="PostgreSQL host")
    postgres_port: int = Field(default=5432, description="PostgreSQL port")
    postgres_db: str = Field(default="trader_bot", description="PostgreSQL database name")
    postgres_user: str = Field(default="trader", description="PostgreSQL user")
    postgres_password: str = Field(default="password", description="PostgreSQL password")

    @computed_field
    @property
    def database_url(self) -> str:
        """Construct async PostgreSQL connection URL."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ==========================================
    # JWT AUTHENTICATION
    # ==========================================
    jwt_secret_key: str = Field(
        default="change_me_in_production_generate_with_openssl_rand_hex_32",
        description="JWT secret key",
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    jwt_access_token_expire_minutes: int = Field(
        default=1440, description="JWT access token expiration (minutes)"
    )

    # ==========================================
    # ADMIN USER (mono-user v1)
    # ==========================================
    admin_username: str = Field(default="admin", description="Admin username")
    admin_password: str = Field(default="admin", description="Admin password")
    admin_email: str = Field(default="admin@localhost", description="Admin email")

    # ==========================================
    # CSRF PROTECTION
    # ==========================================
    csrf_secret_key: str = Field(
        default="generate_csrf_secret_with_openssl_rand_hex_32",
        description="CSRF secret key",
    )
    csrf_token_location: str = Field(default="header", description="CSRF token location")

    # ==========================================
    # RATE LIMITING
    # ==========================================
    rate_limit_enabled: bool = Field(default=True, description="Enable rate limiting")
    rate_limit_login: str = Field(
        default="5/minute", description="Login endpoint rate limit"
    )
    rate_limit_api_read: str = Field(
        default="60/minute", description="Read endpoints rate limit"
    )
    rate_limit_api_write: str = Field(
        default="30/minute", description="Write endpoints rate limit"
    )
    rate_limit_expensive: str = Field(
        default="2/hour", description="Expensive operations rate limit (optimizations)"
    )

    # ==========================================
    # API SERVER
    # ==========================================
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8000, description="API port")
    api_reload: bool = Field(default=True, description="Auto-reload on code changes")
    api_workers: int = Field(default=1, description="Number of workers")

    # ==========================================
    # CORS
    # ==========================================
    cors_origins: str = Field(
        default="http://localhost:5173,http://localhost:5174",
        description="Comma-separated list of allowed CORS origins",
    )

    @computed_field
    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins into list."""
        return [origin.strip() for origin in self.cors_origins.split(",")]

    # ==========================================
    # LOGGING
    # ==========================================
    log_level: str = Field(default="INFO", description="Log level")
    log_format: str = Field(default="json", description="Log format: json or text")
    log_file_enabled: bool = Field(default=False, description="Enable file logging")
    log_file_path: Optional[str] = Field(
        default=None, description="Log file path (if enabled)"
    )

    # ==========================================
    # TRADING BOT CONFIGURATION
    # ==========================================
    # These are defaults that can be overridden via config endpoints

    # Binance
    binance_default_symbol: str = Field(
        default="BTCUSDT", description="Default trading symbol"
    )
    binance_default_timeframe: str = Field(
        default="15m", description="Default timeframe"
    )
    binance_testnet: bool = Field(default=True, description="Use Binance testnet")

    # Strategy
    strategy_entry_threshold: float = Field(
        default=0.6, description="Entry threshold [-1, 1]"
    )
    strategy_exit_threshold: float = Field(
        default=-0.3, description="Exit threshold [-1, 1]"
    )
    strategy_confirmation_candles: int = Field(
        default=2, description="Anti-repainting confirmation candles"
    )

    # Risk management
    risk_max_trades_per_day: int = Field(
        default=5, description="Max trades per day"
    )
    risk_max_exposure_percent: float = Field(
        default=30.0, description="Max exposure as % of capital"
    )
    risk_position_size_mode: str = Field(
        default="confidence", description="Position sizing mode: fixed, confidence, risk_atr"
    )
    risk_fixed_size_usdt: float = Field(
        default=100.0, description="Fixed position size in USDT"
    )
    risk_atr_multiplier: float = Field(
        default=2.0, description="ATR multiplier for risk sizing"
    )
    risk_capital_risk_percent: float = Field(
        default=1.0, description="% of capital to risk per trade (ATR mode)"
    )

    # Stop-loss / Take-profit
    sl_mode: str = Field(default="atr", description="SL mode: atr, fixed")
    sl_atr_multiplier: float = Field(default=2.0, description="SL ATR multiplier")
    sl_fixed_percent: float = Field(default=2.0, description="SL fixed percent")
    tp_mode: str = Field(default="atr", description="TP mode: atr, fixed")
    tp_atr_multiplier: float = Field(default=3.0, description="TP ATR multiplier")
    tp_fixed_percent: float = Field(default=4.0, description="TP fixed percent")

    # Cooldown
    cooldown_after_trade_seconds: int = Field(
        default=3600, description="Cooldown after trade (seconds)"
    )

    # ==========================================
    # OPTUNA OPTIMIZATION
    # ==========================================
    optuna_n_trials: int = Field(default=100, description="Number of Optuna trials")
    optuna_n_jobs: int = Field(
        default=1, description="Parallel jobs (-1 for all CPUs)"
    )
    optuna_sampler: str = Field(
        default="TPE", description="Optuna sampler: TPE, Random, Grid"
    )
    optuna_pruner: str = Field(
        default="MedianPruner", description="Optuna pruner: MedianPruner, HyperbandPruner"
    )

    # ==========================================
    # BACKTESTING
    # ==========================================
    backtest_initial_capital: float = Field(
        default=10000.0, description="Initial capital for backtest"
    )
    backtest_commission_percent: float = Field(
        default=0.1, description="Commission percent (Binance taker fee)"
    )

    @model_validator(mode='after')
    def validate_production_secrets(self):
        """
        Validate that production secrets are strong enough.

        Only validates in production environment (environment='prod').
        Checks JWT secret and database password for minimum length and weak patterns.

        Note: Admin password validation is skipped as Authelia will replace authentication.

        Raises:
            ValueError: If any secret is weak in production mode
        """
        if self.environment == "prod":
            weak_patterns = [
                "change_me", "admin", "password", "secret",
                "generate", "your_", "example", "localhost", "test"
            ]

            # Check JWT secret
            if len(self.jwt_secret_key) < 32:
                raise ValueError(
                    "Production requires JWT_SECRET_KEY >= 32 characters. "
                    "Generate with: openssl rand -hex 32"
                )
            for pattern in weak_patterns:
                if pattern in self.jwt_secret_key.lower():
                    raise ValueError(
                        f"Production JWT_SECRET_KEY contains weak pattern: '{pattern}'. "
                        "Generate with: openssl rand -hex 32"
                    )

            # Check database password
            if len(self.postgres_password) < 16:
                raise ValueError(
                    "Production requires POSTGRES_PASSWORD >= 16 characters. "
                    "Generate with: openssl rand -base64 24"
                )
            for pattern in weak_patterns:
                if pattern in self.postgres_password.lower():
                    raise ValueError(
                        f"Production POSTGRES_PASSWORD contains weak pattern: '{pattern}'. "
                        "Generate with: openssl rand -base64 24"
                    )

            # Skip admin password check - Authelia will replace authentication

        return self


# Global settings instance
settings = Settings()
