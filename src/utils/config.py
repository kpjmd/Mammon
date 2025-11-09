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
        case_sensitive=True,
        extra="ignore",
    )

    # Blockchain Configuration
    cdp_api_key: str = Field(..., description="Coinbase CDP API key")
    cdp_api_secret: str = Field(..., description="Coinbase CDP API secret")
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
