"""Yield scanner agent for monitoring DeFi protocol yields.

This module implements the agent responsible for continuously scanning
all supported DeFi protocols to identify yield opportunities.
"""

import asyncio
from typing import Any, Dict, List, Optional
from decimal import Decimal
from datetime import datetime, UTC, timedelta
from src.protocols.aerodrome import AerodromeProtocol
from src.protocols.morpho import MorphoProtocol
from src.protocols.aave import AaveV3Protocol
from src.protocols.moonwell import MoonwellProtocol
from src.data.oracles import create_price_oracle
from src.security.audit import AuditLogger, AuditEventType, AuditSeverity
from src.utils.logger import get_logger
from src.utils.circuit_breaker import CircuitBreaker

logger = get_logger(__name__)

# Circuit breaker configuration
PROTOCOL_TIMEOUT_SECONDS = 30  # Max time for a single protocol scan
MAX_CONSECUTIVE_FAILURES = 3  # Failures before circuit breaker activates
CIRCUIT_BREAKER_COOLDOWN_SECONDS = 300  # 5 minutes (reduced from 60 minutes for faster recovery)


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

    Phase 3 Sprint 2: Now supports 4 protocols with real mainnet data:
    - Aerodrome (DEX)
    - Morpho (Lending)
    - Aave V3 (Lending)
    - Moonwell (Lending)

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

        # Create shared price oracle to avoid duplicate warnings and improve performance
        chainlink_enabled = config.get("chainlink_enabled", True)
        if chainlink_enabled:
            price_network = config.get("chainlink_price_network", "base-mainnet")
            self.price_oracle = create_price_oracle(
                "chainlink",
                network=config.get("network", "base-mainnet"),
                price_network=price_network,
                cache_ttl_seconds=config.get("chainlink_cache_ttl_seconds", 300),
                max_staleness_seconds=config.get("chainlink_max_staleness_seconds", 3600),
                fallback_to_mock=config.get("chainlink_fallback_to_mock", True),
            )
            logger.info(f"✅ Created shared Chainlink price oracle (price_network={price_network})")
        else:
            self.price_oracle = create_price_oracle("mock")
            logger.info("✅ Created shared mock price oracle")

        # Initialize protocol integrations with shared oracle
        aerodrome_config = {**config, "price_oracle": self.price_oracle}
        self.aerodrome = AerodromeProtocol(aerodrome_config)

        # Phase 3 Sprint 2: Add all lending protocols with read-only mode
        protocol_config = {
            **config,
            "use_mock_data": config.get("use_mock_data", False),  # Real data by default
            "read_only": config.get("read_only", True),
            "price_oracle": self.price_oracle,  # Share oracle across all protocols
        }
        self.morpho = MorphoProtocol(protocol_config)
        self.aave = AaveV3Protocol(protocol_config)
        self.moonwell = MoonwellProtocol(protocol_config)

        self.protocols = [self.aerodrome, self.morpho, self.aave, self.moonwell]

        # Initialize unified circuit breaker for all protocols
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=MAX_CONSECUTIVE_FAILURES,
            timeout_seconds=CIRCUIT_BREAKER_COOLDOWN_SECONDS,
            reset_timeout_seconds=600,  # Reset after 10 minutes of no failures
        )

        logger.info(f"YieldScannerAgent initialized with {len(self.protocols)} protocol(s)")
        logger.info(f"  - Aerodrome (DEX)")
        logger.info(f"  - Morpho (Lending)")
        logger.info(f"  - Aave V3 (Lending)")
        logger.info(f"  - Moonwell (Lending)")
        logger.info(f"🔒 Circuit breaker: {MAX_CONSECUTIVE_FAILURES} failures, {CIRCUIT_BREAKER_COOLDOWN_SECONDS}s timeout")
        if self.dry_run_mode:
            logger.info("🔒 Scanner in DRY RUN mode - no executions will occur")

    async def _scan_single_protocol(self, protocol: Any) -> List[YieldOpportunity]:
        """Scan a single protocol with timeout and circuit breaker.

        Args:
            protocol: Protocol instance to scan

        Returns:
            List of yield opportunities from this protocol
        """
        start_time = datetime.now(UTC)
        opportunities = []

        # Check circuit breaker
        if self.circuit_breaker.is_open(protocol.name):
            logger.warning(f"⚠️  Skipping {protocol.name} - circuit breaker is open")
            return opportunities

        try:
            # Scan protocol with timeout
            logger.info(f"Scanning {protocol.name}...")
            pools = await asyncio.wait_for(
                protocol.get_pools(),
                timeout=PROTOCOL_TIMEOUT_SECONDS
            )

            # Convert pools to opportunities
            for pool in pools:
                opportunity = YieldOpportunity(
                    protocol=protocol.name,
                    pool_id=pool.pool_id,
                    pool_name=pool.name,
                    apy=pool.apy,
                    tvl=pool.tvl,
                    tokens=pool.tokens,
                    metadata=pool.metadata,
                )
                opportunities.append(opportunity)

            # Record success
            scan_duration = (datetime.now(UTC) - start_time).total_seconds()
            self.circuit_breaker.record_success(protocol.name)
            logger.info(
                f"✅ {protocol.name}: {len(pools)} opportunities "
                f"(scanned in {scan_duration:.1f}s)"
            )

        except asyncio.TimeoutError:
            error_msg = f"Timeout after {PROTOCOL_TIMEOUT_SECONDS}s"
            logger.error(f"❌ {protocol.name}: {error_msg}")
            self.circuit_breaker.record_failure(protocol.name, asyncio.TimeoutError(error_msg))

        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ {protocol.name}: {error_msg}")
            self.circuit_breaker.record_failure(protocol.name, e)

        return opportunities

    async def scan_all_protocols(self) -> List[YieldOpportunity]:
        """Scan all supported protocols for yield opportunities.

        Phase 4 Sprint 3: Now uses parallel scanning for 4x performance improvement.
        All 4 protocols (Aerodrome, Morpho, Aave V3, Moonwell) are scanned simultaneously.

        Returns:
            List of yield opportunities sorted by APY (highest first)
        """
        scan_start = datetime.now(UTC)

        # Log scan start
        await self.audit_logger.log_event(
            AuditEventType.YIELD_SCAN,
            AuditSeverity.INFO,
            {"action": "scan_start", "protocols": len(self.protocols)},
        )

        logger.info(f"🔍 Starting PARALLEL scan of {len(self.protocols)} protocols...")

        # Scan all protocols in parallel using asyncio.gather
        protocol_results = await asyncio.gather(
            *[self._scan_single_protocol(protocol) for protocol in self.protocols],
            return_exceptions=False  # Exceptions handled in _scan_single_protocol
        )

        # Flatten results
        all_opportunities = []

        for opportunities in protocol_results:
            all_opportunities.extend(opportunities)

        # Sort by APY (highest first)
        sorted_opportunities = sorted(all_opportunities, key=lambda x: x.apy, reverse=True)

        # Calculate scan duration
        scan_duration = (datetime.now(UTC) - scan_start).total_seconds()

        # Log scan complete with per-protocol metrics
        await self.audit_logger.log_event(
            AuditEventType.YIELD_SCAN,
            AuditSeverity.INFO,
            {
                "action": "scan_complete",
                "opportunities_found": len(sorted_opportunities),
                "top_apy": str(sorted_opportunities[0].apy) if sorted_opportunities else "0",
                "scan_duration_seconds": scan_duration,
                "protocols_scanned": len(self.protocols),
            },
        )

        logger.info(
            f"✅ Parallel scan complete: {len(sorted_opportunities)} opportunities "
            f"found in {scan_duration:.1f}s"
        )
        if sorted_opportunities:
            logger.info(f"   Top yield: {sorted_opportunities[0].protocol} @ {sorted_opportunities[0].apy}% APY")

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

    async def find_best_yield(self, token: str) -> Optional[YieldOpportunity]:
        """Find the highest yield for a specific token across all protocols.

        This is the CORE VALUE PROPOSITION: Find the absolute best yield
        for a given token across all integrated protocols.

        Args:
            token: Token symbol to search for (e.g., 'USDC', 'WETH')

        Returns:
            YieldOpportunity with highest APY for the token, or None if not found
        """
        logger.info(f"🔍 Searching for best {token} yield across all protocols...")

        # Scan all protocols
        all_opportunities = await self.scan_all_protocols()

        # Filter for token
        token_opportunities = [
            opp
            for opp in all_opportunities
            if token.upper() in [t.upper() for t in opp.tokens]
        ]

        if not token_opportunities:
            logger.warning(f"No {token} opportunities found across any protocol")
            return None

        # Already sorted by APY (descending), so first is best
        best = token_opportunities[0]

        # Log results
        logger.info(f"✅ Best {token} yield found:")
        logger.info(f"   Protocol: {best.protocol}")
        logger.info(f"   Pool: {best.pool_name}")
        logger.info(f"   APY: {best.apy}%")
        logger.info(f"   TVL: ${best.tvl:,.0f}")

        # Show comparison to other options
        if len(token_opportunities) > 1:
            second_best = token_opportunities[1]
            advantage = best.apy - second_best.apy
            logger.info(
                f"   Advantage: +{advantage}% over {second_best.protocol} ({second_best.apy}%)"
            )

        # Audit log
        await self.audit_logger.log_event(
            AuditEventType.YIELD_SCAN,
            AuditSeverity.INFO,
            {
                "action": "find_best_yield",
                "token": token,
                "best_protocol": best.protocol,
                "best_apy": str(best.apy),
                "alternatives_count": len(token_opportunities) - 1,
            },
        )

        return best

    async def compare_yields(
        self,
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Enhanced yield comparison analytics across all protocols.

        Provides comprehensive statistics about yield differences to answer
        "how much better?" not just "what's best?".

        Args:
            token: Optional token filter (None = all opportunities)

        Returns:
            Dict with comprehensive yield comparison analytics
        """
        logger.info(f"📊 Running enhanced yield comparison analytics...")

        # Get all opportunities
        all_opportunities = await self.scan_all_protocols()

        # Filter by token if specified
        if token:
            opportunities = [
                opp
                for opp in all_opportunities
                if token.upper() in [t.upper() for t in opp.tokens]
            ]
            logger.info(f"Filtered to {len(opportunities)} {token} opportunities")
        else:
            opportunities = all_opportunities
            logger.info(f"Analyzing all {len(opportunities)} opportunities")

        if not opportunities:
            return {"error": "No opportunities found"}

        # Calculate statistics
        apys = [opp.apy for opp in opportunities]
        best = max(opportunities, key=lambda x: x.apy)
        worst = min(opportunities, key=lambda x: x.apy)

        avg_apy = sum(apys) / len(apys)
        median_apy = sorted(apys)[len(apys) // 2]
        spread = best.apy - worst.apy

        # Calculate volatility (standard deviation)
        variance = sum((apy - avg_apy) ** 2 for apy in apys) / len(apys)
        volatility = variance ** Decimal("0.5")

        # Protocol breakdown
        protocol_stats = {}
        for opp in opportunities:
            if opp.protocol not in protocol_stats:
                protocol_stats[opp.protocol] = {
                    "count": 0,
                    "apys": [],
                    "total_tvl": Decimal(0),
                }
            protocol_stats[opp.protocol]["count"] += 1
            protocol_stats[opp.protocol]["apys"].append(opp.apy)
            protocol_stats[opp.protocol]["total_tvl"] += opp.tvl

        # Calculate average APY per protocol
        for protocol, stats in protocol_stats.items():
            stats["avg_apy"] = sum(stats["apys"]) / len(stats["apys"])
            stats["max_apy"] = max(stats["apys"])
            stats["min_apy"] = min(stats["apys"])

        # Find yield advantages
        if best.apy > avg_apy:
            advantage_over_avg = best.apy - avg_apy
            advantage_pct = (advantage_over_avg / avg_apy) * Decimal(100)
        else:
            advantage_over_avg = Decimal(0)
            advantage_pct = Decimal(0)

        results = {
            "token": token or "ALL",
            "total_opportunities": len(opportunities),
            "best": {
                "protocol": best.protocol,
                "pool": best.pool_name,
                "apy": float(best.apy),
                "tvl": float(best.tvl),
            },
            "worst": {
                "protocol": worst.protocol,
                "pool": worst.pool_name,
                "apy": float(worst.apy),
                "tvl": float(worst.tvl),
            },
            "statistics": {
                "average_apy": float(avg_apy),
                "median_apy": float(median_apy),
                "spread": float(spread),
                "volatility": float(volatility),
                "advantage_over_avg": float(advantage_over_avg),
                "advantage_pct": float(advantage_pct),
            },
            "protocol_breakdown": {
                protocol: {
                    "count": stats["count"],
                    "avg_apy": float(stats["avg_apy"]),
                    "max_apy": float(stats["max_apy"]),
                    "min_apy": float(stats["min_apy"]),
                    "total_tvl": float(stats["total_tvl"]),
                }
                for protocol, stats in protocol_stats.items()
            },
        }

        # Log summary
        logger.info(f"✅ Yield Comparison Summary:")
        logger.info(f"   Best: {best.protocol} @ {best.apy}% APY")
        logger.info(f"   Average: {avg_apy:.2f}% APY")
        logger.info(f"   Spread: {spread:.2f}% ({worst.apy}% to {best.apy}%)")
        logger.info(f"   Best is +{advantage_over_avg:.2f}% over average (+{advantage_pct:.1f}%)")

        return results
