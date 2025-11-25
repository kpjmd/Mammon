"""Database management using SQLAlchemy ORM.

This module handles database connections, session management,
and provides repository patterns for data access.
"""

from typing import Any, Dict, List, Optional, Type, TypeVar
from contextlib import asynccontextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from .models import Base, Position, Transaction, Decision, PerformanceMetric, AuditLog, YieldHistory


T = TypeVar("T", bound=Base)


class Database:
    """Database connection and session manager.

    Provides database initialization, migration support, and
    session management for SQLAlchemy ORM.

    Attributes:
        engine: SQLAlchemy engine
        session_factory: Session factory
    """

    def __init__(self, database_url: str) -> None:
        """Initialize database connection.

        Args:
            database_url: Database connection URL
        """
        self.database_url = database_url
        self.engine = create_engine(database_url)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def create_all_tables(self) -> None:
        """Create all database tables."""
        Base.metadata.create_all(self.engine)

    def drop_all_tables(self) -> None:
        """Drop all database tables (USE WITH CAUTION!)."""
        Base.metadata.drop_all(self.engine)

    @asynccontextmanager
    async def get_session(self) -> Session:
        """Get a database session context manager.

        Yields:
            Database session
        """
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


class BaseRepository:
    """Base repository for data access operations.

    Provides common CRUD operations for all models.

    Attributes:
        session: Database session
        model: SQLAlchemy model class
    """

    def __init__(self, session: Session, model: Type[T]) -> None:
        """Initialize repository.

        Args:
            session: Database session
            model: SQLAlchemy model class
        """
        self.session = session
        self.model = model

    def create(self, **kwargs: Any) -> T:
        """Create a new record.

        Args:
            **kwargs: Model fields

        Returns:
            Created model instance
        """
        instance = self.model(**kwargs)
        self.session.add(instance)
        self.session.flush()  # Flush to get ID without committing
        return instance

    def get_by_id(self, record_id: int) -> Optional[T]:
        """Get record by ID.

        Args:
            record_id: Record ID

        Returns:
            Model instance or None
        """
        return self.session.query(self.model).filter(self.model.id == record_id).first()

    def get_all(self, limit: int = 100, offset: int = 0) -> List[T]:
        """Get all records with pagination.

        Args:
            limit: Maximum records to return
            offset: Number of records to skip

        Returns:
            List of model instances
        """
        return self.session.query(self.model).limit(limit).offset(offset).all()

    def update(self, record_id: int, **kwargs: Any) -> Optional[T]:
        """Update a record.

        Args:
            record_id: Record ID
            **kwargs: Fields to update

        Returns:
            Updated model instance or None
        """
        instance = self.get_by_id(record_id)
        if instance:
            for key, value in kwargs.items():
                if hasattr(instance, key):
                    setattr(instance, key, value)
            self.session.flush()
        return instance

    def delete(self, record_id: int) -> bool:
        """Delete a record.

        Args:
            record_id: Record ID

        Returns:
            True if deleted, False otherwise
        """
        instance = self.get_by_id(record_id)
        if instance:
            self.session.delete(instance)
            self.session.flush()
            return True
        return False


class PositionRepository(BaseRepository):
    """Repository for Position model operations."""

    def __init__(self, session: Session) -> None:
        """Initialize position repository.

        Args:
            session: Database session
        """
        super().__init__(session, Position)

    def get_active_positions(self) -> List[Position]:
        """Get all active positions.

        Returns:
            List of active positions
        """
        return self.session.query(Position).filter(Position.status == "active").all()

    def get_by_protocol(self, protocol: str) -> List[Position]:
        """Get all positions for a specific protocol.

        Args:
            protocol: Protocol name

        Returns:
            List of positions for the protocol
        """
        return self.session.query(Position).filter(Position.protocol == protocol).all()

    def get_by_wallet(self, wallet_address: str) -> List[Position]:
        """Get all positions for a wallet address.

        Args:
            wallet_address: Wallet address

        Returns:
            List of positions for the wallet
        """
        return self.session.query(Position).filter(Position.wallet_address == wallet_address).all()


class TransactionRepository(BaseRepository):
    """Repository for Transaction model operations."""

    def __init__(self, session: Session) -> None:
        """Initialize transaction repository.

        Args:
            session: Database session
        """
        super().__init__(session, Transaction)

    def get_recent_transactions(self, limit: int = 10) -> List[Transaction]:
        """Get recent transactions.

        Args:
            limit: Number of transactions to return

        Returns:
            List of recent transactions
        """
        return (
            self.session.query(Transaction)
            .order_by(Transaction.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_by_status(self, status: str) -> List[Transaction]:
        """Get transactions by status.

        Args:
            status: Transaction status ('pending', 'completed', 'failed')

        Returns:
            List of transactions with the given status
        """
        return self.session.query(Transaction).filter(Transaction.status == status).all()

    def get_by_hash(self, tx_hash: str) -> Optional[Transaction]:
        """Get transaction by hash.

        Args:
            tx_hash: Transaction hash

        Returns:
            Transaction or None
        """
        return self.session.query(Transaction).filter(Transaction.tx_hash == tx_hash).first()


class YieldHistoryRepository(BaseRepository):
    """Repository for YieldHistory model operations."""

    def __init__(self, session: Session) -> None:
        """Initialize yield history repository.

        Args:
            session: Database session
        """
        super().__init__(session, YieldHistory)

    def record_snapshot(self, pool: "Pool") -> YieldHistory:
        """Record a yield snapshot from a Pool instance.

        Args:
            pool: Pool instance to snapshot

        Returns:
            Created YieldHistory record
        """
        import json
        from datetime import datetime

        return self.create(
            protocol=pool.protocol,
            pool_id=pool.pool_id,
            pool_name=pool.name,
            apy=pool.apy,
            borrow_apy=pool.borrow_apy,
            tvl=pool.tvl,
            utilization=pool.utilization,
            tokens=json.dumps(pool.tokens),
            snapshot_timestamp=datetime.utcnow(),
            metadata=json.dumps(pool.metadata) if pool.metadata else None,
        )

    def get_by_protocol(self, protocol: str, limit: int = 100) -> List[YieldHistory]:
        """Get yield history for a specific protocol.

        Args:
            protocol: Protocol name
            limit: Maximum records to return

        Returns:
            List of yield history records
        """
        return (
            self.session.query(YieldHistory)
            .filter(YieldHistory.protocol == protocol)
            .order_by(YieldHistory.snapshot_timestamp.desc())
            .limit(limit)
            .all()
        )

    def get_by_pool(self, pool_id: str, limit: int = 100) -> List[YieldHistory]:
        """Get yield history for a specific pool.

        Args:
            pool_id: Pool identifier
            limit: Maximum records to return

        Returns:
            List of yield history records
        """
        return (
            self.session.query(YieldHistory)
            .filter(YieldHistory.pool_id == pool_id)
            .order_by(YieldHistory.snapshot_timestamp.desc())
            .limit(limit)
            .all()
        )

    def get_time_range(
        self,
        start_time: "datetime",
        end_time: "datetime",
        protocol: Optional[str] = None,
        pool_id: Optional[str] = None,
    ) -> List[YieldHistory]:
        """Get yield history within a time range.

        Args:
            start_time: Start of time range
            end_time: End of time range
            protocol: Optional protocol filter
            pool_id: Optional pool filter

        Returns:
            List of yield history records
        """
        query = self.session.query(YieldHistory).filter(
            YieldHistory.snapshot_timestamp >= start_time,
            YieldHistory.snapshot_timestamp <= end_time,
        )

        if protocol:
            query = query.filter(YieldHistory.protocol == protocol)
        if pool_id:
            query = query.filter(YieldHistory.pool_id == pool_id)

        return query.order_by(YieldHistory.snapshot_timestamp.desc()).all()

    def get_latest_snapshot(self, pool_id: str) -> Optional[YieldHistory]:
        """Get the most recent snapshot for a pool.

        Args:
            pool_id: Pool identifier

        Returns:
            Most recent YieldHistory record or None
        """
        return (
            self.session.query(YieldHistory)
            .filter(YieldHistory.pool_id == pool_id)
            .order_by(YieldHistory.snapshot_timestamp.desc())
            .first()
        )
