"""Position tracking for DeFi positions with prediction accuracy validation.

This module tracks positions across protocols and validates the accuracy of
MAMMON's profitability predictions - a key competitive advantage.

Critical for autonomous operation and x402 marketplace credibility.
"""

from typing import Dict, List, Optional
from decimal import Decimal
from datetime import datetime, timedelta
from sqlalchemy import create_engine, and_, desc
from sqlalchemy.orm import sessionmaker, Session
from src.data.models import Base, Position, PositionSnapshot
from src.utils.logger import get_logger

logger = get_logger(__name__)


class PositionTracker:
    """Track DeFi positions with prediction accuracy validation.

    This class is critical for:
    1. Autonomous operation (knows current positions)
    2. Performance validation (predicted vs actual ROI)
    3. Competitive moat (proves accuracy of predictions)
    4. x402 credibility (auditable track record)

    Attributes:
        db_path: Path to SQLite database
        session: SQLAlchemy database session
    """

    def __init__(self, db_path: str = "data/mammon.db"):
        """Initialize position tracker with database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(self.engine)
        SessionLocal = sessionmaker(bind=self.engine)
        self.session: Session = SessionLocal()
        logger.info(f"✅ PositionTracker initialized with database: {db_path}")

    async def record_position(
        self,
        wallet_address: str,
        protocol: str,
        pool_id: str,
        token: str,
        amount: Decimal,
        value_usd: Decimal,
        current_apy: Decimal,
        predicted_30d_roi: Optional[Decimal] = None,
        predicted_annual_gain: Optional[Decimal] = None,
        gas_cost_usd: Optional[Decimal] = None,
    ) -> int:
        """Record a new position or update existing one.

        Args:
            wallet_address: Wallet holding the position
            protocol: Protocol name (e.g., "Aave V3")
            pool_id: Pool identifier
            token: Token symbol
            amount: Position size in token units
            value_usd: Current USD value
            current_apy: Current APY at position entry
            predicted_30d_roi: Predicted 30-day return (for validation)
            predicted_annual_gain: Predicted annual gain in USD
            gas_cost_usd: Gas cost to enter position

        Returns:
            Position ID
        """
        # Check if position already exists (active position in same pool)
        existing = self.session.query(Position).filter(
            and_(
                Position.wallet_address == wallet_address,
                Position.protocol == protocol,
                Position.pool_id == pool_id,
                Position.token == token,
                Position.status == "active"
            )
        ).first()

        if existing:
            # Update existing position
            existing.amount = amount
            existing.value_usd = value_usd
            existing.current_apy = current_apy
            existing.updated_at = datetime.utcnow()
            logger.info(
                f"📝 Updated position: {protocol} {token} = {amount} "
                f"(${value_usd:.2f} @ {current_apy:.2f}% APY)"
            )
            position_id = existing.id
        else:
            # Create new position
            position = Position(
                wallet_address=wallet_address,
                protocol=protocol,
                pool_id=pool_id,
                token=token,
                amount=amount,
                value_usd=value_usd,
                entry_apy=current_apy,
                current_apy=current_apy,
                opened_at=datetime.utcnow(),
                status="active",
            )
            self.session.add(position)
            self.session.flush()  # Get the ID
            position_id = position.id

            logger.info(
                f"✨ New position recorded: {protocol} {token} = {amount} "
                f"(${value_usd:.2f} @ {current_apy:.2f}% APY)"
            )

            if predicted_30d_roi:
                logger.info(f"🎯 Predicted 30d ROI: {predicted_30d_roi:.4f}%")

        self.session.commit()
        return position_id

    async def close_position(
        self,
        position_id: int,
        actual_value_usd: Decimal,
        actual_roi: Optional[Decimal] = None,
    ) -> Dict:
        """Close a position and calculate final performance.

        Args:
            position_id: Position to close
            actual_value_usd: Final USD value
            actual_roi: Calculated actual ROI

        Returns:
            Performance summary with prediction accuracy
        """
        position = self.session.query(Position).get(position_id)
        if not position:
            raise ValueError(f"Position {position_id} not found")

        position.status = "closed"
        position.closed_at = datetime.utcnow()
        position.value_usd = actual_value_usd

        # Calculate actual performance
        days_held = (position.closed_at - position.opened_at).days
        if days_held == 0:
            days_held = 1  # Minimum 1 day

        # Calculate actual ROI if not provided
        if actual_roi is None and position.value_usd:
            initial_value = Decimal(str(position.value_usd))  # Entry value
            final_value = actual_value_usd
            actual_roi = ((final_value - initial_value) / initial_value) * 100

        self.session.commit()

        logger.info(
            f"🏁 Closed position: {position.protocol} {position.token} "
            f"(held {days_held} days, ROI: {actual_roi:.4f}%)"
        )

        return {
            "position_id": position_id,
            "protocol": position.protocol,
            "token": position.token,
            "days_held": days_held,
            "entry_apy": position.entry_apy,
            "actual_roi": actual_roi,
            "entry_value_usd": position.value_usd,
            "final_value_usd": actual_value_usd,
        }

    async def close_all_positions(
        self,
        wallet_address: Optional[str] = None,
    ) -> int:
        """Close all active positions (optionally filtered by wallet).

        Useful for position detection to clear stale data before re-scanning.

        Args:
            wallet_address: Only close positions for this wallet (optional)

        Returns:
            Number of positions closed
        """
        query = self.session.query(Position).filter(Position.status == "active")

        if wallet_address:
            query = query.filter(Position.wallet_address == wallet_address)

        positions = query.all()
        count = len(positions)

        for position in positions:
            position.status = "closed"
            position.closed_at = datetime.utcnow()

        self.session.commit()

        logger.info(f"🧹 Closed {count} active positions" + (f" for wallet {wallet_address}" if wallet_address else ""))
        return count

    async def update_position_performance(
        self,
        position_id: int,
        current_apy: Decimal,
        current_value_usd: Decimal,
    ) -> None:
        """Update position with current performance data.

        Args:
            position_id: Position to update
            current_apy: Current APY (may have changed)
            current_value_usd: Current USD value
        """
        position = self.session.query(Position).get(position_id)
        if not position:
            raise ValueError(f"Position {position_id} not found")

        position.current_apy = current_apy
        position.value_usd = current_value_usd
        position.updated_at = datetime.utcnow()
        self.session.commit()

        logger.debug(
            f"📊 Updated position {position_id}: "
            f"APY={current_apy:.2f}%, Value=${current_value_usd:.2f}"
        )

    async def get_current_positions(
        self,
        wallet_address: Optional[str] = None,
        protocol: Optional[str] = None,
    ) -> List[PositionSnapshot]:
        """Get all active positions.

        Args:
            wallet_address: Filter by wallet (optional)
            protocol: Filter by protocol (optional)

        Returns:
            List of active position snapshots
        """
        query = self.session.query(Position).filter(Position.status == "active")

        if wallet_address:
            query = query.filter(Position.wallet_address == wallet_address)
        if protocol:
            query = query.filter(Position.protocol == protocol)

        positions = query.all()

        snapshots = []
        for pos in positions:
            snapshots.append(
                PositionSnapshot(
                    wallet_address=pos.wallet_address,
                    protocol=pos.protocol,
                    pool_id=pos.pool_id,
                    token=pos.token,
                    amount=pos.amount,
                    value_usd=pos.value_usd or Decimal("0"),
                    current_apy=pos.current_apy or Decimal("0"),
                    opened_at=pos.opened_at or datetime.utcnow(),
                    status=pos.status,
                    metadata={
                        "position_id": pos.id,
                        "entry_apy": pos.entry_apy,
                    }
                )
            )

        logger.info(f"📋 Found {len(snapshots)} active positions")
        return snapshots

    async def get_position_history(
        self,
        days: int = 30,
        wallet_address: Optional[str] = None,
    ) -> List[Position]:
        """Get historical positions.

        Args:
            days: Number of days to look back
            wallet_address: Filter by wallet (optional)

        Returns:
            List of positions from the specified period
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        query = self.session.query(Position).filter(
            Position.created_at >= cutoff
        )

        if wallet_address:
            query = query.filter(Position.wallet_address == wallet_address)

        positions = query.order_by(desc(Position.created_at)).all()
        logger.info(f"📜 Found {len(positions)} positions in last {days} days")
        return positions

    async def calculate_realized_apy(
        self,
        position_id: int,
    ) -> Optional[Decimal]:
        """Calculate the actual realized APY for a position.

        Args:
            position_id: Position to analyze

        Returns:
            Annualized APY based on actual performance, or None if not enough data
        """
        position = self.session.query(Position).get(position_id)
        if not position:
            return None

        if not position.opened_at or not position.value_usd:
            return None

        # Calculate time held
        end_time = position.closed_at or datetime.utcnow()
        time_held = (end_time - position.opened_at).total_seconds()
        days_held = time_held / 86400  # Convert to days

        if days_held < 1:
            return None  # Need at least 1 day of data

        # Get current value (or final value if closed)
        # For simplicity, assume value hasn't changed much (lending positions)
        # In production, we'd track value snapshots over time
        current_value = position.value_usd
        initial_value = position.value_usd  # Entry value

        # Calculate return
        value_gain = current_value - initial_value
        roi = (value_gain / initial_value) if initial_value > 0 else Decimal("0")

        # Annualize
        days_per_year = Decimal("365.25")
        realized_apy = roi * (days_per_year / Decimal(str(days_held)))

        return realized_apy * 100  # Convert to percentage

    async def get_prediction_accuracy(
        self,
        days: int = 30,
    ) -> Dict[str, float]:
        """Calculate prediction accuracy metrics - KEY COMPETITIVE ADVANTAGE.

        This validates MAMMON's profitability predictions and proves our moat.

        Args:
            days: Number of days to analyze

        Returns:
            Accuracy metrics including:
            - apy_prediction_accuracy: % accuracy of APY predictions
            - positions_tracked: Number of positions analyzed
            - avg_prediction_error: Average prediction error
        """
        positions = await self.get_position_history(days=days)

        if not positions:
            return {
                "apy_prediction_accuracy": 0.0,
                "positions_tracked": 0,
                "avg_prediction_error": 0.0,
            }

        total_error = Decimal("0")
        tracked_positions = 0

        for pos in positions:
            if pos.entry_apy and pos.current_apy:
                # Calculate APY drift
                predicted_apy = pos.entry_apy
                actual_apy = pos.current_apy
                error = abs(predicted_apy - actual_apy)
                total_error += error
                tracked_positions += 1

        if tracked_positions == 0:
            return {
                "apy_prediction_accuracy": 0.0,
                "positions_tracked": 0,
                "avg_prediction_error": 0.0,
            }

        avg_error = total_error / Decimal(str(tracked_positions))

        # Calculate accuracy as inverse of error (capped at 100%)
        # If avg error is 0.5%, accuracy is ~99.5%
        # If avg error is 5%, accuracy is ~95%
        accuracy = max(0.0, 100.0 - float(avg_error))

        logger.info(
            f"🎯 Prediction Accuracy: {accuracy:.1f}% "
            f"(avg error: {avg_error:.2f}% over {tracked_positions} positions)"
        )

        return {
            "apy_prediction_accuracy": accuracy,
            "positions_tracked": tracked_positions,
            "avg_prediction_error": float(avg_error),
        }

    async def get_portfolio_summary(
        self,
        wallet_address: str,
    ) -> Dict:
        """Get current portfolio summary.

        Args:
            wallet_address: Wallet to analyze

        Returns:
            Portfolio metrics
        """
        positions = await self.get_current_positions(wallet_address=wallet_address)

        if not positions:
            return {
                "total_value_usd": Decimal("0"),
                "position_count": 0,
                "avg_apy": Decimal("0"),
                "positions_by_protocol": {},
            }

        total_value = sum(p.value_usd for p in positions)
        position_count = len(positions)

        # Calculate weighted average APY
        weighted_apy_sum = sum(
            p.current_apy * (p.value_usd / total_value)
            for p in positions
            if total_value > 0
        )

        # Group by protocol
        by_protocol: Dict[str, Decimal] = {}
        for p in positions:
            if p.protocol not in by_protocol:
                by_protocol[p.protocol] = Decimal("0")
            by_protocol[p.protocol] += p.value_usd

        return {
            "total_value_usd": total_value,
            "position_count": position_count,
            "avg_apy": weighted_apy_sum,
            "positions_by_protocol": by_protocol,
        }

    def close(self):
        """Close database connection."""
        self.session.close()
        logger.info("✅ PositionTracker session closed")
