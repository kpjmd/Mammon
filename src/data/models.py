"""Data models for MAMMON's database schema.

This module defines SQLAlchemy models for storing agent state,
transactions, decisions, and performance history.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional
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
    protocol = Column(String(50), nullable=False)
    pool_id = Column(String(100), nullable=False)
    token = Column(String(20), nullable=False)
    amount = Column(Numeric(precision=36, scale=18), nullable=False)
    value_usd = Column(Numeric(precision=20, scale=2), nullable=False)
    entry_apy = Column(Numeric(precision=10, scale=6), nullable=False)
    current_apy = Column(Numeric(precision=10, scale=6), nullable=False)
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
