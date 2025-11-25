"""Configuration management with Pydantic validation.

This module provides type-safe configuration loading from environment
variables with validation and security checks.
"""

from decimal import Decimal
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from src.utils.networks import validate_network, get_supported_networks


class Settings(BaseSettings):
    """MAMMON configuration settings.

    All settings are loaded from environment variables with
    type validation and security checks.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,  # Allow uppercase env vars to match lowercase fields
        extra="ignore",
    )

    # Blockchain Configuration
    cdp_api_key: str = Field(..., description="Coinbase CDP API key")
    cdp_api_secret: str = Field(..., description="Coinbase CDP API secret")
    cdp_wallet_secret: str = Field(..., description="CDP wallet secret (base64-encoded, NEVER commit!)")
    cdp_wallet_id: Optional[str] = Field(
        default=None,
        description="CDP wallet ID for persistent wallet (get from import script)",
    )
    wallet_seed: str = Field(..., description="Wallet seed phrase - BIP39 mnemonic (12 or 24 words, NEVER commit!)")
    wallet_id: Optional[str] = Field(
        default=None,
        description="CDP wallet ID (auto-generated on first run)",
    )
    base_rpc_url: str = Field(
        default="https://sepolia.base.org",
        description="Base network RPC URL",
    )
    network: str = Field(
        default="base-sepolia",
        description="Network to connect to (base-sepolia, base-mainnet, arbitrum-sepolia, arbitrum-mainnet)",
    )

    # AI Configuration
    anthropic_api_key: str = Field(..., description="Anthropic API key for Claude")

    # Security Limits (USD values)
    max_transaction_value_usd: Decimal = Field(
        default=Decimal("1000"),
        description="Maximum single transaction value",
        ge=0,
    )
    daily_spending_limit_usd: Decimal = Field(
        default=Decimal("5000"),
        description="Maximum daily spending limit",
        ge=0,
    )
    approval_threshold_usd: Decimal = Field(
        default=Decimal("100"),
        description="Transaction amount requiring approval",
        ge=0,
    )
    x402_daily_budget_usd: Decimal = Field(
        default=Decimal("50"),
        description="Daily budget for x402 service purchases",
        ge=0,
    )
    max_gas_price_gwei: Decimal = Field(
        default=Decimal("100"),
        description="Maximum gas price in gwei (reject transactions if exceeded)",
        ge=0,
    )

    # Local Wallet Configuration
    use_local_wallet: bool = Field(
        default=True,
        description="Use local wallet (seed phrase) instead of CDP wallet",
    )
    max_priority_fee_gwei: Decimal = Field(
        default=Decimal("2"),
        description="Maximum priority fee in gwei for EIP-1559 transactions",
        ge=0,
    )
    gas_buffer_simple: float = Field(
        default=1.5,
        description="Gas buffer multiplier for simple operations (<50k gas)",
        ge=1.0,
        le=3.0,
    )
    gas_buffer_moderate: float = Field(
        default=1.3,
        description="Gas buffer multiplier for moderate operations (50k-200k gas)",
        ge=1.0,
        le=3.0,
    )
    gas_buffer_complex: float = Field(
        default=1.2,
        description="Gas buffer multiplier for complex operations (>200k gas)",
        ge=1.0,
        le=3.0,
    )

    # Environment
    environment: str = Field(
        default="development",
        description="Environment: development, staging, production",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level: DEBUG, INFO, WARNING, ERROR",
    )

    # Database
    database_url: str = Field(
        default="sqlite:///mammon.db",
        description="Database connection URL",
    )

    # Monitoring (Optional)
    alert_webhook: Optional[str] = Field(
        None,
        description="Webhook URL for alerts",
    )
    sentry_dsn: Optional[str] = Field(
        None,
        description="Sentry DSN for error tracking",
    )

    # Safety Features
    dry_run_mode: bool = Field(
        default=True,
        description="Enable dry-run mode (simulates transactions, no real execution)",
    )

    # Chainlink Oracle Configuration
    chainlink_enabled: bool = Field(
        default=True,
        description="Enable Chainlink price oracles (use mock oracle if False)",
    )
    chainlink_price_network: str = Field(
        default="base-mainnet",
        description="Network to query Chainlink prices from (typically base-mainnet for reliability)",
    )
    chainlink_cache_ttl_seconds: int = Field(
        default=300,
        description="Chainlink price cache TTL in seconds (5 minutes default)",
        ge=60,  # Minimum 1 minute
        le=3600,  # Maximum 1 hour
    )
    chainlink_max_staleness_seconds: int = Field(
        default=3600,
        description="Maximum acceptable age for Chainlink prices (1 hour default)",
        ge=300,  # Minimum 5 minutes
        le=86400,  # Maximum 24 hours
    )
    chainlink_fallback_to_mock: bool = Field(
        default=True,
        description="Fallback to mock oracle if Chainlink unavailable",
    )
    base_mainnet_rpc_url: str = Field(
        default="https://mainnet.base.org",
        description="Base Mainnet RPC URL for price oracle queries (read-only)",
    )

    # Premium RPC Configuration (Sprint 4 Priority 2)
    alchemy_api_key: Optional[str] = Field(
        default=None,
        description="Alchemy API key for premium RPC access (optional, improves reliability)",
    )
    quicknode_endpoint: Optional[str] = Field(
        default=None,
        description="QuickNode endpoint URL for backup RPC (optional)",
    )

    # RPC Rate Limiting (requests per second)
    alchemy_rate_limit_per_second: int = Field(
        default=100,
        description="Alchemy rate limit (RPS)",
        ge=1,
        le=1000,
    )
    quicknode_rate_limit_per_second: int = Field(
        default=25,
        description="QuickNode rate limit (RPS)",
        ge=1,
        le=1000,
    )
    public_rate_limit_per_second: int = Field(
        default=10,
        description="Public RPC rate limit (RPS)",
        ge=1,
        le=100,
    )

    # Protocol Scanning Configuration (Performance Optimization)
    morpho_max_markets: int = Field(
        default=20,
        description="Maximum Morpho markets to scan (limits from 100+ to improve scan speed)",
        ge=5,
        le=100,
    )
    aerodrome_max_pools: int = Field(
        default=10,
        description="Maximum Aerodrome pools to scan",
        ge=5,
        le=50,
    )
    supported_tokens: str = Field(
        default="ETH,WETH,USDC,USDT,DAI,BTC,WBTC",
        description="Comma-separated list of supported tokens with Chainlink feeds",
    )

    # Circuit Breaker Settings
    rpc_failure_threshold: int = Field(
        default=3,
        description="Consecutive failures before circuit breaker opens",
        ge=1,
        le=10,
    )
    rpc_recovery_timeout: int = Field(
        default=60,
        description="Seconds before circuit breaker attempts recovery",
        ge=30,
        le=300,
    )

    # Gradual Rollout Configuration
    premium_rpc_enabled: bool = Field(
        default=False,
        description="Enable premium RPC endpoints (requires alchemy_api_key)",
    )
    premium_rpc_percentage: int = Field(
        default=10,
        description="Percentage of requests routed to premium RPC (0-100)",
        ge=0,
        le=100,
    )

    # RPC Health Monitoring
    rpc_health_check_interval: int = Field(
        default=60,
        description="Interval in seconds for RPC endpoint health checks",
        ge=30,
        le=600,
    )

    # ScheduledOptimizer Configuration (Phase 4 Sprint 2)
    scan_interval_hours: int = Field(
        default=4,
        description="Hours between automated yield scans",
        ge=1,
        le=24,
    )
    max_rebalances_per_day: int = Field(
        default=5,
        description="Maximum automated rebalances per 24-hour period",
        ge=1,
        le=20,
    )
    max_gas_per_day_usd: Decimal = Field(
        default=Decimal("50"),
        description="Maximum gas spending per 24-hour period (USD)",
        ge=0,
    )
    min_profit_usd: Decimal = Field(
        default=Decimal("10"),
        description="Minimum annual profit required to execute rebalance (USD)",
        ge=0,
    )
    min_apy_improvement: Decimal = Field(
        default=Decimal("0.5"),
        description="Minimum APY improvement required (percentage points)",
        ge=0,
    )
    min_rebalance_amount: Decimal = Field(
        default=Decimal("100"),
        description="Minimum amount for rebalance consideration (USD)",
        ge=0,
    )
    max_break_even_days: int = Field(
        default=30,
        description="Maximum acceptable days to break even on gas costs",
        ge=1,
        le=365,
    )
    max_cost_pct: Decimal = Field(
        default=Decimal("0.01"),
        description="Maximum gas cost as percentage of rebalance amount (1% = 0.01)",
        ge=0,
        le=Decimal("0.1"),
    )

    @field_validator("cdp_api_key", "cdp_api_secret", "anthropic_api_key")
    @classmethod
    def validate_required_secrets(cls, v: str, info) -> str:
        """Validate that required secrets are not placeholder values.

        Args:
            v: Field value
            info: Validation info

        Returns:
            Validated value

        Raises:
            ValueError: If value is a placeholder
        """
        if not v or v.startswith("your_") or v.endswith("_here"):
            raise ValueError(
                f"{info.field_name} must be set to a real value, not a placeholder"
            )
        return v

    @field_validator("wallet_seed")
    @classmethod
    def validate_wallet_seed(cls, v: str) -> str:
        """Validate wallet seed is a proper BIP39 mnemonic phrase.

        Args:
            v: Wallet seed value

        Returns:
            Validated seed phrase

        Raises:
            ValueError: If seed is invalid
        """
        # Check for empty/None (Pydantic handles None, but check empty string)
        if not v or not v.strip():
            raise ValueError(
                "wallet_seed is required. Generate a BIP39 seed phrase.\n"
                "  - NEVER share or commit your seed phrase!"
            )

        # Check for placeholders
        if v.startswith("your_") or v.endswith("_here"):
            raise ValueError(
                "wallet_seed must be a real BIP39 seed phrase, not a placeholder"
            )

        # Basic validation: should be 12-24 words
        word_count = len(v.strip().split())
        if word_count not in (12, 15, 18, 21, 24):
            raise ValueError(
                f"Invalid BIP39 seed phrase: found {word_count} words, "
                f"expected 12, 15, 18, 21, or 24 words"
            )

        return v.strip()

    @field_validator("network")
    @classmethod
    def validate_network_id(cls, v: str) -> str:
        """Validate network ID against supported networks.

        Args:
            v: Network ID value

        Returns:
            Validated network ID

        Raises:
            ValueError: If network is not supported
        """
        if not validate_network(v):
            supported = ", ".join(get_supported_networks())
            raise ValueError(
                f"Unsupported network: {v}. "
                f"Supported networks: {supported}"
            )
        return v

    @field_validator("chainlink_price_network")
    @classmethod
    def validate_price_network_id(cls, v: str) -> str:
        """Validate Chainlink price network against supported networks.

        Args:
            v: Price network ID value

        Returns:
            Validated network ID

        Raises:
            ValueError: If network is not supported
        """
        if not validate_network(v):
            supported = ", ".join(get_supported_networks())
            raise ValueError(
                f"Unsupported chainlink_price_network: {v}. "
                f"Supported networks: {supported}"
            )
        return v

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment value.

        Args:
            v: Environment value

        Returns:
            Validated value

        Raises:
            ValueError: If environment is invalid
        """
        allowed = {"development", "staging", "production"}
        if v not in allowed:
            raise ValueError(f"environment must be one of {allowed}")
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level value.

        Args:
            v: Log level value

        Returns:
            Validated value (uppercase)

        Raises:
            ValueError: If log level is invalid
        """
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return v_upper

    @field_validator("dry_run_mode")
    @classmethod
    def validate_dry_run_mode(cls, v: bool, info) -> bool:
        """Validate dry-run mode and warn if disabled in non-production.

        Args:
            v: Dry-run mode value
            info: Validation info

        Returns:
            Validated value
        """
        environment = info.data.get("environment", "development")

        if environment != "production" and not v:
            print("⚠️  WARNING: Dry-run mode is DISABLED in non-production environment!")
            print("⚠️  Real transactions will be executed. This may use real funds.")
            print("⚠️  Set DRY_RUN_MODE=true in .env to enable safe mode.")

        if v:
            print("🔒 Dry-run mode ENABLED - All transactions will be simulated")

        return v

    @field_validator("premium_rpc_enabled")
    @classmethod
    def validate_premium_rpc(cls, v: bool, info) -> bool:
        """Validate premium RPC configuration.

        Args:
            v: Premium RPC enabled value
            info: Validation info

        Returns:
            Validated value

        Raises:
            ValueError: If premium RPC enabled but no API key provided
        """
        if v:
            alchemy_key = info.data.get("alchemy_api_key")
            if not alchemy_key:
                raise ValueError(
                    "premium_rpc_enabled=true requires alchemy_api_key to be set. "
                    "Either provide an Alchemy API key or set premium_rpc_enabled=false."
                )
            print("🚀 Premium RPC enabled with Alchemy")

        return v

    def is_production(self) -> bool:
        """Check if running in production environment.

        Returns:
            True if production, False otherwise
        """
        return self.environment == "production"

    def is_development(self) -> bool:
        """Check if running in development environment.

        Returns:
            True if development, False otherwise
        """
        return self.environment == "development"


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the global settings instance.

    Lazy loads settings on first access.

    Returns:
        Settings instance
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Reload settings from environment.

    Useful for testing or configuration changes.

    Returns:
        New settings instance
    """
    global _settings
    _settings = Settings()
    return _settings
