"""Configurable yield snapshot scheduler.

Provides manual and automatic yield snapshot recording
for historical tracking and trend analysis.
"""

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from src.utils.logger import get_logger
from src.data.database import Database, YieldHistoryRepository
from src.data.models import Pool

logger = get_logger(__name__)


class YieldSnapshotScheduler:
    """Scheduler for recording yield snapshots.

    Supports both manual snapshots (development) and automatic
    hourly snapshots (production).

    Attributes:
        database: Database instance
        mode: 'manual' or 'hourly'
        interval_seconds: Snapshot interval (3600 for hourly)
        running: Whether scheduler is running
    """

    def __init__(
        self,
        database: Database,
        mode: str = "manual",
        interval_seconds: int = 3600,  # 1 hour default
    ) -> None:
        """Initialize snapshot scheduler.

        Args:
            database: Database instance
            mode: 'manual' or 'hourly'
            interval_seconds: Seconds between snapshots (hourly mode)
        """
        self.database = database
        self.mode = mode
        self.interval_seconds = interval_seconds
        self.running = False

        if mode not in ["manual", "hourly"]:
            raise ValueError(f"Invalid mode: {mode}. Must be 'manual' or 'hourly'")

        logger.info(
            f"YieldSnapshotScheduler initialized: mode={mode}, "
            f"interval={interval_seconds}s"
        )

    async def record_snapshot(self, pools: List[Pool]) -> int:
        """Record yield snapshots for a list of pools.

        Args:
            pools: List of Pool instances to snapshot

        Returns:
            Number of snapshots recorded
        """
        async with self.database.get_session() as session:
            repo = YieldHistoryRepository(session)
            count = 0

            for pool in pools:
                try:
                    repo.record_snapshot(pool)
                    count += 1
                except Exception as e:
                    logger.error(
                        f"Failed to record snapshot for {pool.protocol}/{pool.pool_id}: {e}"
                    )

            logger.info(f"Recorded {count}/{len(pools)} yield snapshots")
            return count

    async def start_hourly(
        self,
        pool_fetcher_func,  # Async function that returns List[Pool]
    ) -> None:
        """Start automatic hourly snapshot recording.

        Args:
            pool_fetcher_func: Async function that returns current pools
        """
        if self.mode != "hourly":
            logger.warning("Cannot start hourly mode when mode={self.mode}")
            return

        if self.running:
            logger.warning("Snapshot scheduler already running")
            return

        self.running = True
        logger.info(
            f"Starting hourly snapshot scheduler (interval={self.interval_seconds}s)"
        )

        try:
            while self.running:
                try:
                    # Fetch current pools
                    pools = await pool_fetcher_func()

                    # Record snapshots
                    count = await self.record_snapshot(pools)
                    logger.info(f"Hourly snapshot: recorded {count} pools")

                    # Wait for next interval
                    await asyncio.sleep(self.interval_seconds)

                except Exception as e:
                    logger.error(f"Error in hourly snapshot loop: {e}")
                    # Continue running despite errors
                    await asyncio.sleep(60)  # Wait 1 minute before retrying

        except asyncio.CancelledError:
            logger.info("Hourly snapshot scheduler cancelled")
            self.running = False
            raise

    def stop(self) -> None:
        """Stop the automatic snapshot scheduler."""
        if self.running:
            logger.info("Stopping hourly snapshot scheduler")
            self.running = False
        else:
            logger.warning("Snapshot scheduler not running")


def create_snapshot_scheduler(
    database: Database,
    mode: str = "manual",
    interval_seconds: int = 3600,
) -> YieldSnapshotScheduler:
    """Factory function to create a yield snapshot scheduler.

    Args:
        database: Database instance
        mode: 'manual' or 'hourly'
        interval_seconds: Seconds between snapshots (hourly mode only)

    Returns:
        Configured YieldSnapshotScheduler instance
    """
    return YieldSnapshotScheduler(
        database=database,
        mode=mode,
        interval_seconds=interval_seconds,
    )
