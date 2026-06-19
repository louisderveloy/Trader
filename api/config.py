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
    # AUTHENTICATION MODE
    # ==========================================
    # local         -> built-in JWT-cookie login (mono-user). Only mode usable in dev.
    # authelia_oidc -> Authelia (auth.trader.derveloy.eu) as an OIDC provider; the API is a
    #                  confidential Relying Party (Authorization Code + PKCE). PROD-ONLY and
    #                  MANDATORY in prod (validate_production_secrets enforces it).
    auth_mode: str = Field(default="local", description="Auth mode: local or authelia_oidc")

    # ==========================================
    # AUTHELIA OIDC (prod-only relying party)
    # ==========================================
    # Issuer base URL; the RP discovers endpoints via {issuer}/.well-known/openid-configuration.
    authelia_oidc_issuer: str = Field(
        default="", description="Authelia OIDC issuer URL, e.g. https://auth.trader.derveloy.eu"
    )
    authelia_oidc_client_id: str = Field(
        default="", description="OIDC client_id registered in Authelia for the API (trader-api)"
    )
    authelia_oidc_client_secret: str = Field(
        default="", description="OIDC client secret (confidential client); >=32 chars in prod"
    )
    # Public base URL of the API, used to build the OIDC redirect_uri(s). No trailing slash.
    api_public_base_url: str = Field(
        default="http://localhost:8000",
        description="Public base URL of the API (used for OIDC redirect URIs)",
    )
    # Public base URL of the dashboard, used for post-login / no-access redirects. No trailing slash.
    dashboard_public_base_url: str = Field(
        default="http://localhost:5173",
        description="Public base URL of the dashboard (post-login redirect target)",
    )
    # Dedicated key encrypting the short-lived OIDC transaction cookie (state/nonce/PKCE).
    # MUST be distinct from jwt_secret_key and csrf_secret_key. >=32 chars in prod.
    oidc_transaction_secret: str = Field(
        default="generate_oidc_txn_secret_with_openssl_rand_hex_32",
        description="Encryption key for the OIDC transaction cookie (state/nonce/PKCE)",
    )
    # Authelia group names mapped to internal roles. Membership is read from the id_token
    # `groups` claim; an identity in neither group is denied access (no session issued).
    oidc_admin_group: str = Field(default="admins", description="Authelia group → Role.ADMIN")
    oidc_viewer_group: str = Field(default="viewers", description="Authelia group → Role.VIEWER")
    # Step-up freshness: a live-run authorization requires a re-authentication whose auth_time
    # is no older than this many seconds.
    oidc_stepup_max_age_seconds: int = Field(
        default=300, description="Max age (s) of step-up re-authentication for live runs"
    )
    # DEV-ONLY auth bypass: when environment==dev AND auth_mode==local, the synthesized
    # principal's groups are taken from here (comma-separated). Refused in prod.
    dev_user_group: str = Field(
        default="admins", description="DEV-ONLY: synthesized groups when auth is disabled"
    )

    @computed_field
    @property
    def dev_user_groups_list(self) -> list[str]:
        """Parse the dev bypass groups into a list."""
        return [g.strip() for g in self.dev_user_group.split(",") if g.strip()]

    # ==========================================
    # ADMIN USER (mono-user v1)
    # ==========================================
    admin_username: str = Field(default="admin", description="Admin username")
    admin_password: str = Field(default="admin", description="Admin password (dev fallback if no hash set)")
    admin_password_hash: str = Field(
        default="",
        description="Bcrypt hash of the admin password; takes precedence over admin_password when set",
    )
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
        default="BTCUSDC", description="Default trading symbol (USDC only; USDT not authorised in EU)"
    )
    # Symbols offered in the dashboard's run-start combo box. Comma-separated;
    # the first entry is treated as the default. USDC quote only.
    available_symbols: str = Field(
        default="BTCUSDC", description="Comma-separated list of selectable trading symbols"
    )

    @computed_field
    @property
    def available_symbols_list(self) -> list[str]:
        """Parse available symbols into an upper-cased, de-duplicated list."""
        seen: list[str] = []
        for raw in self.available_symbols.split(","):
            sym = raw.strip().upper()
            if sym and sym not in seen:
                seen.append(sym)
        return seen or [self.binance_default_symbol.upper()]
    binance_default_timeframe: str = Field(
        default="15m", description="Default timeframe"
    )

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
    # RUN CONTROL (start/stop/kill + logs)
    # ==========================================
    bot_logs_dir: str = Field(
        default="/var/log/trader-bot",
        description="Directory holding per-run log files (mounted read-only from the bot volume)",
    )
    run_logs_max_lines: int = Field(
        default=100, description="Max log lines returned by the run logs endpoint"
    )
    max_concurrent_backtests: int = Field(
        default=2, description="Max simultaneously active backtests (API + supervisor cap)"
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
    paper_initial_capital: float = Field(
        default=1000.0, description="Default simulated initial capital for paper trading"
    )

    @model_validator(mode='after')
    def validate_production_secrets(self):
        """
        Validate that production secrets are strong enough.

        Only validates in production environment (environment='prod').
        Checks JWT secret and database password for minimum length and weak patterns.

        Note: Admin password validation is skipped because production forces
        AUTH_MODE=authelia_oidc (the local password path returns 404 in that mode —
        see api/auth/routes.py). These two facts are load-bearing on each other:
        the skip is only safe because the local login is disabled in OIDC mode.

        Raises:
            ValueError: If any secret is weak or auth is misconfigured in production
        """
        if self.environment == "prod":
            weak_patterns = [
                "change_me", "admin", "password", "secret",
                "generate", "your_", "example", "localhost", "test"
            ]

            # Production MUST run Authelia OIDC. AUTH_MODE=local is a dev-only mode whose
            # DEV_USER_GROUP bypass is a total authentication bypass; refuse to boot so it
            # can never be reachable in production.
            if self.auth_mode != "authelia_oidc":
                raise ValueError(
                    "Production requires AUTH_MODE=authelia_oidc. "
                    "AUTH_MODE=local is a dev-only mode and must never run in production."
                )

            # Reject wildcard CORS origins in production (credentials are sent with requests).
            for origin in self.cors_origins_list:
                if origin == "*" or "*" in origin:
                    raise ValueError(
                        f"Production CORS_ORIGINS must be explicit; wildcard not allowed: {origin!r}"
                    )

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

            # Skip admin password check - Authelia replaces authentication in prod
            # (and the local /auth/login path returns 404 when auth_mode != local).

            # OIDC relying-party configuration must be present and strong.
            if not self.authelia_oidc_issuer.startswith("https://"):
                raise ValueError(
                    "Production requires AUTHELIA_OIDC_ISSUER to be an https:// URL."
                )
            if not self.authelia_oidc_client_id:
                raise ValueError("Production requires AUTHELIA_OIDC_CLIENT_ID to be set.")
            if len(self.authelia_oidc_client_secret) < 32:
                raise ValueError(
                    "Production requires AUTHELIA_OIDC_CLIENT_SECRET >= 32 characters. "
                    "Generate with: openssl rand -hex 32"
                )
            for pattern in weak_patterns:
                if pattern in self.authelia_oidc_client_secret.lower():
                    raise ValueError(
                        f"Production AUTHELIA_OIDC_CLIENT_SECRET contains weak pattern: '{pattern}'."
                    )

            # Dedicated OIDC transaction-cookie encryption key (must not reuse other secrets).
            if len(self.oidc_transaction_secret) < 32:
                raise ValueError(
                    "Production requires OIDC_TRANSACTION_SECRET >= 32 characters. "
                    "Generate with: openssl rand -hex 32"
                )
            for pattern in weak_patterns:
                if pattern in self.oidc_transaction_secret.lower():
                    raise ValueError(
                        f"Production OIDC_TRANSACTION_SECRET contains weak pattern: '{pattern}'."
                    )
            if self.oidc_transaction_secret in (self.jwt_secret_key, self.csrf_secret_key):
                raise ValueError(
                    "OIDC_TRANSACTION_SECRET must be distinct from JWT_SECRET_KEY and CSRF_SECRET_KEY."
                )

        return self


# Global settings instance
settings = Settings()
