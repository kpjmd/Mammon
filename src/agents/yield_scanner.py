"""Yield scanner agent for monitoring DeFi protocol yields.

This module implements the agent responsible for continuously scanning
all supported DeFi protocols to identify yield opportunities.
"""

from typing import Any, Dict, List
from decimal import Decimal
from src.protocols.aerodrome import AerodromeProtocol
from src.security.audit import AuditLogger, AuditEventType, AuditSeverity
from src.utils.logger import get_logger

logger = get_logger(__name__)


class YieldOpportunity:
    """Represents a yield opportunity from a DeFi protocol.

    Attributes:
        protocol: Name of the protocol
        pool_id: Identifier of the specific pool/vault
        pool_name: Human-readable pool name
        apy: Annual percentage yield
        tvl: Total value locked
        tokens: List of token symbols in the pool
        metadata: Additional pool metadata
    """

    def __init__(
        self,
        protocol: str,
        pool_id: str,
        pool_name: str,
        apy: Decimal,
        tvl: Decimal,
        tokens: List[str],
        metadata: Dict[str, Any] = None,
    ) -> None:
        """Initialize a yield opportunity.

        Args:
            protocol: Protocol name (e.g., 'Aerodrome', 'Morpho')
            pool_id: Pool/vault identifier
            pool_name: Pool name
            apy: Annual percentage yield
            tvl: Total value locked in USD
            tokens: List of token symbols
            metadata: Additional metadata
        """
        self.protocol = protocol
        self.pool_id = pool_id
        self.pool_name = pool_name
        self.apy = apy
        self.tvl = tvl
        self.tokens = tokens
        self.metadata = metadata or {}


class YieldScannerAgent:
    """Agent for scanning and comparing yields across DeFi protocols.

    Continuously monitors supported protocols to identify the best
    yield opportunities for available assets.

    Phase 1B: Focuses on Aerodrome protocol.
    Phase 2+: Will add Morpho, Moonwell, Aave, Beefy.

    Attributes:
        config: Configuration settings
        dry_run_mode: If True, only scans but doesn't execute
        protocols: List of protocol integrations
        audit_logger: Audit logging instance
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize the yield scanner agent.

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.dry_run_mode = config.get("dry_run_mode", True)
        self.audit_logger = AuditLogger()

        # Initialize protocol integrations
        self.aerodrome = AerodromeProtocol(config)
        self.protocols = [self.aerodrome]

        logger.info(f"YieldScannerAgent initialized with {len(self.protocols)} protocol(s)")
        if self.dry_run_mode:
            logger.info("🔒 Scanner in DRY RUN mode - no executions will occur")

    async def scan_all_protocols(self) -> List[YieldOpportunity]:
        """Scan all supported protocols for yield opportunities.

        Returns:
            List of yield opportunities sorted by APY (highest first)
        """
        # Log scan start
        await self.audit_logger.log_event(
            AuditEventType.YIELD_SCAN,
            AuditSeverity.INFO,
            {"action": "scan_start", "protocols": len(self.protocols)},
        )

        all_opportunities = []

        # Scan Aerodrome (Phase 1B)
        try:
            logger.info("Scanning Aerodrome for yield opportunities...")
            pools = await self.aerodrome.get_pools()

            for pool in pools:
                opportunity = YieldOpportunity(
                    protocol="Aerodrome",
                    pool_id=pool.pool_id,
                    pool_name=pool.name,
                    apy=pool.apy,
                    tvl=pool.tvl,
                    tokens=pool.tokens,
                    metadata=pool.metadata,
                )
                all_opportunities.append(opportunity)

            logger.info(f"Found {len(pools)} opportunities on Aerodrome")

        except Exception as e:
            logger.error(f"Failed to scan Aerodrome: {e}")

        # Sort by APY (highest first)
        sorted_opportunities = sorted(all_opportunities, key=lambda x: x.apy, reverse=True)

        # Log scan complete
        await self.audit_logger.log_event(
            AuditEventType.YIELD_SCAN,
            AuditSeverity.INFO,
            {
                "action": "scan_complete",
                "opportunities_found": len(sorted_opportunities),
                "top_apy": str(sorted_opportunities[0].apy) if sorted_opportunities else "0",
            },
        )

        logger.info(f"Scan complete: {len(sorted_opportunities)} total opportunities")
        return sorted_opportunities

    async def get_best_opportunities(
        self,
        token: str = None,
        min_apy: Decimal = Decimal("0"),
        min_tvl: Decimal = Decimal("0"),
    ) -> List[YieldOpportunity]:
        """Find best yield opportunities, optionally filtered by token.

        Args:
            token: Token symbol to filter by (None = all tokens)
            min_apy: Minimum acceptable APY (default: 0)
            min_tvl: Minimum acceptable TVL for safety (default: 0)

        Returns:
            Filtered and sorted list of opportunities
        """
        # Get all opportunities
        all_opportunities = await self.scan_all_protocols()

        # Filter by criteria
        filtered = []
        for opp in all_opportunities:
            # Check APY threshold
            if opp.apy < min_apy:
                continue

            # Check TVL threshold
            if opp.tvl < min_tvl:
                continue

            # Check token filter (if specified)
            if token and token.upper() not in [t.upper() for t in opp.tokens]:
                continue

            filtered.append(opp)

        logger.info(
            f"Filtered opportunities: {len(filtered)} of {len(all_opportunities)} "
            f"(APY >= {min_apy}%, TVL >= ${min_tvl:,.0f})"
        )

        # Display top 5
        logger.info("📊 Top 5 Opportunities:")
        for i, opp in enumerate(filtered[:5], 1):
            tokens_str = "/".join(opp.tokens)
            logger.info(
                f"  {i}. {opp.protocol} - {tokens_str}: {opp.apy}% APY (${opp.tvl:,.0f} TVL)"
            )

        return filtered

    async def compare_current_position(
        self,
        current_protocol: str,
        current_pool_id: str,
        current_apy: Decimal,
    ) -> Dict[str, Any]:
        """Compare current position against available alternatives.

        Args:
            current_protocol: Current protocol name
            current_pool_id: Current pool ID
            current_apy: Current APY being earned

        Returns:
            Comparison results with potential improvements
        """
        # Get all opportunities
        all_opportunities = await self.scan_all_protocols()

        # Find better opportunities
        better_opportunities = [opp for opp in all_opportunities if opp.apy > current_apy]

        # Calculate potential gains
        if better_opportunities:
            best_alternative = better_opportunities[0]  # Already sorted by APY
            apy_improvement = best_alternative.apy - current_apy
            potential_gain_pct = (apy_improvement / current_apy * 100) if current_apy > 0 else 0

            logger.info(f"Found {len(better_opportunities)} better opportunities")
            logger.info(
                f"Best alternative: {best_alternative.protocol} - {best_alternative.pool_name}"
            )
            logger.info(
                f"Potential improvement: +{apy_improvement}% APY (+{potential_gain_pct:.1f}% relative)"
            )

            recommendation = (
                "REBALANCE"
                if potential_gain_pct > 10
                else "CONSIDER" if potential_gain_pct > 5 else "HOLD"
            )
        else:
            best_alternative = None
            apy_improvement = Decimal("0")
            potential_gain_pct = Decimal("0")
            recommendation = "OPTIMAL"

            logger.info("Current position is optimal - no better alternatives found")

        return {
            "current": {
                "protocol": current_protocol,
                "pool_id": current_pool_id,
                "apy": current_apy,
            },
            "best_alternative": {
                "protocol": best_alternative.protocol if best_alternative else None,
                "pool_id": best_alternative.pool_id if best_alternative else None,
                "pool_name": best_alternative.pool_name if best_alternative else None,
                "apy": best_alternative.apy if best_alternative else Decimal("0"),
            }
            if best_alternative
            else None,
            "apy_improvement": apy_improvement,
            "potential_gain_pct": potential_gain_pct,
            "recommendation": recommendation,
            "better_opportunities_count": len(better_opportunities),
        }
