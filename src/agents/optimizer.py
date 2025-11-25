"""Optimizer agent for orchestrating yield optimization.

This module implements the main orchestration agent that coordinates
between YieldScanner, strategies, and decision-making components to
generate actionable rebalancing recommendations.

Phase 3 Sprint 3: Orchestrates the complete optimization flow:
1. Scan all protocols for yields (YieldScannerAgent)
2. Analyze opportunities (SimpleYield or RiskAdjusted strategy)
3. Generate recommendations with audit logging
"""

from typing import Any, Dict, List
from decimal import Decimal
from src.agents.yield_scanner import YieldScannerAgent, YieldOpportunity
from src.strategies.base_strategy import BaseStrategy, RebalanceRecommendation
from src.security.audit import AuditLogger, AuditEventType, AuditSeverity
from src.utils.logger import get_logger

logger = get_logger(__name__)


class OptimizerAgent:
    """Orchestrates the complete yield optimization process.

    Coordinates between YieldScanner (protocol queries), Strategy
    (decision logic), and audit logging to generate actionable
    rebalancing recommendations.

    This is MAMMON's main optimization engine, integrating all
    Sprint 3 components into a cohesive workflow.

    Attributes:
        config: Configuration settings
        scanner: YieldScannerAgent instance
        strategy: Strategy instance (SimpleYield or RiskAdjusted)
        audit_logger: AuditLogger instance
        dry_run_mode: If True, only generates recommendations without execution
    """

    def __init__(
        self,
        config: Dict[str, Any],
        scanner: YieldScannerAgent,
        strategy: BaseStrategy,
    ) -> None:
        """Initialize the optimizer agent.

        Args:
            config: Configuration dictionary
            scanner: YieldScannerAgent for protocol queries
            strategy: Strategy for optimization logic
        """
        self.config = config
        self.scanner = scanner
        self.strategy = strategy
        self.audit_logger = AuditLogger()
        self.dry_run_mode = config.get("dry_run_mode", True)

        logger.info(
            f"OptimizerAgent initialized with strategy: {strategy.name}"
        )
        if self.dry_run_mode:
            logger.info("🔒 Optimizer in DRY RUN mode - no executions will occur")

    async def find_rebalance_opportunities(
        self,
        current_positions: Dict[str, Decimal],
    ) -> List[RebalanceRecommendation]:
        """Find optimal rebalancing opportunities for current positions.

        This is the main optimization workflow that:
        1. Scans all protocols for current yields
        2. Converts scanner output to strategy input format
        3. Calls strategy to analyze opportunities
        4. Audit logs all recommendations
        5. Returns actionable recommendations

        Args:
            current_positions: Current positions as Dict[protocol, amount_usd]
                Example: {"Aave V3": Decimal("1000"), "Morpho": Decimal("500")}

        Returns:
            List of rebalance recommendations, sorted by confidence
        """
        logger.info(
            f"Finding rebalance opportunities for {len(current_positions)} positions"
        )

        # Log optimization start
        await self.audit_logger.log_event(
            AuditEventType.YIELD_SCAN,
            AuditSeverity.INFO,
            "Starting rebalance optimization",
            metadata={
                "action": "optimization_start",
                "strategy": self.strategy.name,
                "num_positions": len(current_positions),
                "positions": {k: str(v) for k, v in current_positions.items()},
            },
        )

        # Step 1: Scan all protocols for current yields
        try:
            opportunities = await self.scanner.scan_all_protocols()
            logger.info(f"Found {len(opportunities)} yield opportunities across protocols")
        except Exception as e:
            logger.error(f"Failed to scan protocols: {e}")
            await self.audit_logger.log_event(
                AuditEventType.YIELD_SCAN,
                AuditSeverity.ERROR,
                f"Protocol scan failed: {e}",
                metadata={"error": str(e)},
            )
            return []

        # Handle empty opportunities
        if not opportunities:
            logger.warning("No yield opportunities found")
            await self.audit_logger.log_event(
                AuditEventType.YIELD_SCAN,
                AuditSeverity.WARNING,
                "No yield opportunities available",
                metadata={"action": "optimization_aborted"},
            )
            return []

        # Step 2: Convert YieldOpportunity objects to Dict[protocol, apy]
        available_yields = self._build_yields_dictionary(opportunities)
        logger.info(
            f"Built yields dictionary with {len(available_yields)} protocols"
        )

        # Handle empty positions
        if not current_positions:
            logger.info("No current positions to rebalance")
            return []

        # Step 3: Call strategy to analyze opportunities
        try:
            recommendations = await self.strategy.analyze_opportunities(
                current_positions=current_positions,
                available_yields=available_yields,
            )
            logger.info(f"Strategy generated {len(recommendations)} recommendations")
        except Exception as e:
            logger.error(f"Strategy analysis failed: {e}")
            await self.audit_logger.log_event(
                AuditEventType.YIELD_SCAN,
                AuditSeverity.ERROR,
                f"Strategy analysis failed: {e}",
                metadata={"error": str(e), "strategy": self.strategy.name},
            )
            return []

        # Step 4: Audit log all recommendations
        await self._log_recommendations(recommendations, current_positions)

        # Step 5: Sort by confidence and return
        sorted_recommendations = sorted(
            recommendations,
            key=lambda r: r.confidence,
            reverse=True,
        )

        logger.info(
            f"✅ Optimization complete: {len(sorted_recommendations)} recommendations"
        )
        return sorted_recommendations

    async def optimize_new_allocation(
        self,
        total_capital: Decimal,
    ) -> Dict[str, Decimal]:
        """Optimize allocation for new capital.

        Determines optimal allocation across protocols for new capital
        deployment based on current yields and strategy logic.

        Args:
            total_capital: Total capital to allocate in USD

        Returns:
            Dict mapping protocol to allocation amount
            Example: {"Aave V3": Decimal("5000"), "Morpho": Decimal("5000")}
        """
        logger.info(f"Optimizing allocation for ${total_capital:,.2f} new capital")

        # Log allocation start
        await self.audit_logger.log_event(
            AuditEventType.YIELD_SCAN,
            AuditSeverity.INFO,
            "Starting new allocation optimization",
            metadata={
                "action": "allocation_start",
                "strategy": self.strategy.name,
                "total_capital": str(total_capital),
            },
        )

        # Step 1: Scan all protocols for current yields
        try:
            opportunities = await self.scanner.scan_all_protocols()
            logger.info(f"Found {len(opportunities)} yield opportunities")
        except Exception as e:
            logger.error(f"Failed to scan protocols: {e}")
            await self.audit_logger.log_event(
                AuditEventType.YIELD_SCAN,
                AuditSeverity.ERROR,
                f"Protocol scan failed: {e}",
                metadata={"error": str(e)},
            )
            return {}

        # Handle empty opportunities
        if not opportunities:
            logger.warning("No yield opportunities found for allocation")
            await self.audit_logger.log_event(
                AuditEventType.YIELD_SCAN,
                AuditSeverity.WARNING,
                "No yield opportunities available for allocation",
                metadata={"action": "allocation_aborted"},
            )
            return {}

        # Step 2: Convert to yields dictionary
        available_yields = self._build_yields_dictionary(opportunities)

        # Step 3: Call strategy to calculate optimal allocation
        try:
            allocation = self.strategy.calculate_optimal_allocation(
                total_capital=total_capital,
                opportunities=available_yields,
            )
            logger.info(
                f"Strategy allocated capital across {len(allocation)} protocols"
            )
        except Exception as e:
            logger.error(f"Allocation calculation failed: {e}")
            await self.audit_logger.log_event(
                AuditEventType.YIELD_SCAN,
                AuditSeverity.ERROR,
                f"Allocation calculation failed: {e}",
                metadata={"error": str(e), "strategy": self.strategy.name},
            )
            return {}

        # Step 4: Audit log allocation
        await self.audit_logger.log_event(
            AuditEventType.YIELD_SCAN,
            AuditSeverity.INFO,
            "Allocation optimization complete",
            metadata={
                "action": "allocation_complete",
                "strategy": self.strategy.name,
                "total_capital": str(total_capital),
                "num_protocols": len(allocation),
                "allocation": {k: str(v) for k, v in allocation.items()},
            },
        )

        # Log allocation breakdown
        logger.info("📊 Optimal Allocation:")
        for protocol, amount in sorted(
            allocation.items(), key=lambda x: x[1], reverse=True
        ):
            pct = (amount / total_capital * 100) if total_capital > 0 else 0
            logger.info(f"  {protocol}: ${amount:,.2f} ({pct:.1f}%)")

        logger.info(f"✅ Allocation complete: {len(allocation)} protocols")
        return allocation

    def _build_yields_dictionary(
        self,
        opportunities: List[YieldOpportunity],
    ) -> Dict[str, Decimal]:
        """Convert YieldOpportunity list to protocol->APY dictionary.

        Takes the highest APY for each protocol (across all pools).

        Args:
            opportunities: List of YieldOpportunity objects from scanner

        Returns:
            Dict mapping protocol name to best APY
            Example: {"Aave V3": Decimal("5.5"), "Morpho": Decimal("7.2")}
        """
        logger.info(f"🔍 DEBUG: _build_yields_dictionary() called with {len(opportunities)} opportunities")
        yields_dict: Dict[str, Decimal] = {}

        for i, opp in enumerate(opportunities):
            protocol = opp.protocol
            apy = opp.apy

            if i < 5:  # Log first 5 opportunities
                logger.info(f"🔍 DEBUG: Opportunity {i+1}: protocol='{protocol}', apy={apy}%, pool={opp.pool_id}")

            # Keep the highest APY for each protocol
            if protocol not in yields_dict or apy > yields_dict[protocol]:
                yields_dict[protocol] = apy

        logger.info(f"🔍 DEBUG: Built yields dictionary with {len(yields_dict)} protocols:")
        for protocol, apy in sorted(yields_dict.items(), key=lambda x: x[1], reverse=True)[:10]:
            logger.info(f"🔍 DEBUG:   '{protocol}': {apy}%")

        return yields_dict

    async def _log_recommendations(
        self,
        recommendations: List[RebalanceRecommendation],
        current_positions: Dict[str, Decimal],
    ) -> None:
        """Audit log all rebalance recommendations.

        Args:
            recommendations: List of recommendations to log
            current_positions: Current positions for context
        """
        if not recommendations:
            await self.audit_logger.log_event(
                AuditEventType.YIELD_SCAN,
                AuditSeverity.INFO,
                "No profitable rebalance opportunities found",
                metadata={
                    "action": "optimization_complete",
                    "strategy": self.strategy.name,
                    "num_recommendations": 0,
                    "current_positions": {k: str(v) for k, v in current_positions.items()},
                },
            )
            return

        # Log summary
        await self.audit_logger.log_event(
            AuditEventType.YIELD_SCAN,
            AuditSeverity.INFO,
            f"Generated {len(recommendations)} rebalance recommendations",
            metadata={
                "action": "optimization_complete",
                "strategy": self.strategy.name,
                "num_recommendations": len(recommendations),
                "recommendations": [
                    {
                        "from": rec.from_protocol,
                        "to": rec.to_protocol,
                        "token": rec.token,
                        "amount": str(rec.amount),
                        "expected_apy": str(rec.expected_apy),
                        "confidence": rec.confidence,
                        "reason": rec.reason,
                    }
                    for rec in recommendations
                ],
            },
        )

        # Log each recommendation individually for detailed audit trail
        for i, rec in enumerate(recommendations, 1):
            await self.audit_logger.log_event(
                AuditEventType.YIELD_SCAN,
                AuditSeverity.INFO,
                f"Recommendation {i}: {rec.from_protocol} → {rec.to_protocol}",
                metadata={
                    "action": "recommendation_generated",
                    "recommendation_index": i,
                    "from_protocol": rec.from_protocol,
                    "to_protocol": rec.to_protocol,
                    "token": rec.token,
                    "amount": str(rec.amount),
                    "expected_apy": str(rec.expected_apy),
                    "confidence": rec.confidence,
                    "reason": rec.reason,
                },
            )
