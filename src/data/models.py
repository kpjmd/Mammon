"""Data models for MAMMON's database schema.

This module defines SQLAlchemy models for storing agent state,
transactions, decisions, and performance history.

Also includes dataclass models for runtime data structures.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from sqlalchemy import Column, Integer, String, DateTime, Numeric, Text, ForeignKey
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


class Position(Base):
    """Represents a DeFi position.

    Tracks current positions across protocols for portfolio management.
    """

    __tablename__ = "positions"

    id = Column(Integer, primary_key=True)
    wallet_address = Column(String(42), nullable=False)  # Ethereum address
    protocol = Column(String(50), nullable=False)
    pool_id = Column(String(100), nullable=False)
    token = Column(String(20), nullable=False)
    amount = Column(Numeric(precision=36, scale=18), nullable=False)
    value_usd = Column(Numeric(precision=20, scale=2), nullable=True)
    entry_apy = Column(Numeric(precision=10, scale=6), nullable=True)
    current_apy = Column(Numeric(precision=10, scale=6), nullable=True)
    opened_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="active")  # 'active', 'closed'
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Transaction(Base):
    """Represents a blockchain transaction.

    Stores complete transaction history for audit and analysis.
    """

    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    tx_hash = Column(String(66), unique=True, nullable=False)
    from_protocol = Column(String(50), nullable=True)
    to_protocol = Column(String(50), nullable=True)
    operation = Column(String(20), nullable=False)  # deposit, withdraw, rebalance
    token = Column(String(20), nullable=False)
    amount = Column(Numeric(precision=36, scale=18), nullable=False)
    gas_used = Column(Integer, nullable=True)
    gas_price = Column(Numeric(precision=20, scale=0), nullable=True)
    status = Column(String(20), nullable=False)  # pending, completed, failed
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class Decision(Base):
    """Represents an agent decision.

    Logs all optimization decisions for auditability and learning.
    """

    __tablename__ = "decisions"

    id = Column(Integer, primary_key=True)
    decision_type = Column(String(50), nullable=False)  # rebalance, hold, etc.
    rationale = Column(Text, nullable=False)
    from_protocol = Column(String(50), nullable=True)
    to_protocol = Column(String(50), nullable=True)
    expected_apy_improvement = Column(Numeric(precision=10, scale=6), nullable=True)
    risk_score = Column(Integer, nullable=True)
    approved = Column(Integer, default=0)  # 0=pending, 1=approved, -1=rejected
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    transaction = relationship("Transaction", backref="decision")


class PerformanceMetric(Base):
    """Tracks performance metrics over time.

    Stores daily/hourly snapshots of portfolio performance.
    """

    __tablename__ = "performance_metrics"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False)
    total_value_usd = Column(Numeric(precision=20, scale=2), nullable=False)
    daily_yield = Column(Numeric(precision=20, scale=8), nullable=True)
    average_apy = Column(Numeric(precision=10, scale=6), nullable=True)
    gas_spent_usd = Column(Numeric(precision=20, scale=2), nullable=True)
    num_rebalances = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    """Audit log for critical operations.

    Comprehensive logging for security and compliance.
    """

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    event_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)  # info, warning, error, critical
    message = Column(Text, nullable=False)
    event_data = Column(Text, nullable=True)  # JSON string
    user = Column(String(100), nullable=True)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class YieldHistory(Base):
    """Historical yield snapshots for trend analysis.

    Stores time-series data of yields across all protocols for
    tracking trends, identifying opportunities, and making
    rebalancing decisions.
    """

    __tablename__ = "yield_history"

    id = Column(Integer, primary_key=True)
    protocol = Column(String(50), nullable=False)
    pool_id = Column(String(100), nullable=False)
    pool_name = Column(String(200), nullable=False)
    apy = Column(Numeric(precision=10, scale=6), nullable=False)
    borrow_apy = Column(Numeric(precision=10, scale=6), nullable=True)
    tvl = Column(Numeric(precision=20, scale=2), nullable=False)
    utilization = Column(Numeric(precision=5, scale=4), nullable=True)
    tokens = Column(Text, nullable=False)  # JSON array
    snapshot_timestamp = Column(DateTime, nullable=False)
    pool_metadata = Column(Text, nullable=True)  # JSON string (renamed from 'metadata')
    created_at = Column(DateTime, default=datetime.utcnow)


# ============================================================================
# Runtime Dataclass Models
# ============================================================================


@dataclass
class Pool:
    """Represents a lending/liquidity pool across protocols.

    Protocol-agnostic pool representation for comparing yields
    across different DeFi protocols. Consolidated to include yield
    opportunity calculations.

    Attributes:
        pool_id: Unique pool identifier
        protocol: Protocol name ('Morpho', 'Aave', 'Aerodrome', etc.)
        name: Human-readable pool name
        tokens: List of token symbols in the pool
        apy: Supply APY (annual percentage yield)
        tvl: Total value locked in USD
        address: Pool contract address
        borrow_apy: Borrow APY (for lending protocols)
        utilization: Pool utilization rate (0-1)
        risk_score: Risk assessment score (0-100, optional)
        net_apy: Net APY after gas costs (computed)
        estimated_gas_cost: Estimated gas cost in USD
        break_even_days: Days to break even on gas costs
        projected_30d_profit: Projected 30-day profit in USD
        confidence_score: Confidence in the opportunity (0-1)
        metadata: Protocol-specific additional data
    """

    pool_id: str
    protocol: str
    name: str
    tokens: List[str]
    apy: Decimal
    tvl: Decimal
    address: str = ""
    borrow_apy: Optional[Decimal] = None
    utilization: Decimal = Decimal(0)
    risk_score: Optional[int] = None
    net_apy: Optional[Decimal] = None  # APY after gas costs
    estimated_gas_cost: Decimal = Decimal(0)
    break_even_days: Optional[int] = None
    projected_30d_profit: Decimal = Decimal(0)
    confidence_score: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


# Type alias for backward compatibility
YieldOpportunity = Pool


@dataclass
class PositionSnapshot:
    """Runtime snapshot of a DeFi position.

    Used for tracking current positions before persisting to database.

    Attributes:
        wallet_address: User's wallet address
        protocol: Protocol name
        pool_id: Pool identifier
        token: Token symbol
        amount: Position amount
        value_usd: Current value in USD
        current_apy: Current APY
        opened_at: When position was opened
        status: Position status ('active', 'closed')
        metadata: Additional position data
    """

    wallet_address: str
    protocol: str
    pool_id: str
    token: str
    amount: Decimal
    value_usd: Decimal
    current_apy: Decimal
    opened_at: datetime = field(default_factory=datetime.utcnow)
    status: str = "active"
    metadata: Dict[str, Any] = field(default_factory=dict)
