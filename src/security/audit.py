"""Audit logging for compliance and security monitoring.

This module provides comprehensive audit logging for all critical
operations, creating an immutable audit trail.
"""

from typing import Any, Dict, Optional
from datetime import datetime, UTC
from enum import Enum
import json


class AuditEventType(Enum):
    """Types of auditable events."""

    TRANSACTION_INITIATED = "transaction_initiated"
    TRANSACTION_APPROVED = "transaction_approved"
    TRANSACTION_REJECTED = "transaction_rejected"
    TRANSACTION_SIGNED = "transaction_signed"
    TRANSACTION_EXECUTED = "transaction_executed"
    TRANSACTION_SUBMITTED = "transaction_submitted"
    TRANSACTION_COMPLETED = "transaction_completed"
    TRANSACTION_FAILED = "transaction_failed"
    CONFIG_CHANGED = "config_changed"
    LIMIT_EXCEEDED = "limit_exceeded"
    APPROVAL_REQUESTED = "approval_requested"
    RISK_ALERT = "risk_alert"
    SECURITY_VIOLATION = "security_violation"
    WALLET_EXPORT = "wallet_export"
    POOL_QUERY = "pool_query"
    YIELD_SCAN = "yield_scan"
    WALLET_INITIALIZED = "wallet_initialized"
    # Sprint 3: Risk assessment events
    RISK_CHECK = "risk_check"
    # Sprint 4: Rebalance execution events
    REBALANCE_OPPORTUNITY_FOUND = "rebalance_opportunity_found"
    REBALANCE_EXECUTED = "rebalance_executed"
    # Sprint 4 Priority 2: RPC events
    RPC_REQUEST = "rpc_request"
    RPC_USAGE_SUMMARY = "rpc_usage_summary"
    RPC_ENDPOINT_FAILURE = "rpc_endpoint_failure"
    RPC_CIRCUIT_BREAKER_OPENED = "rpc_circuit_breaker_opened"


class AuditSeverity(Enum):
    """Severity levels for audit events."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AuditLogger:
    """Comprehensive audit logging system.

    Logs all critical operations with full context for security
    monitoring, compliance, and debugging.

    Attributes:
        log_file: Path to audit log file
        database: Optional database for structured logging
    """

    def __init__(
        self,
        log_file: str = "audit.log",
        database: Optional[Any] = None,
    ) -> None:
        """Initialize the audit logger.

        Args:
            log_file: Path to audit log file
            database: Optional database connection
        """
        self.log_file = log_file
        self.database = database

    async def log_event(
        self,
        event_type: AuditEventType,
        severity: AuditSeverity,
        message: str,
        metadata: Optional[Dict[str, Any]] = None,
        user: Optional[str] = None,
    ) -> None:
        """Log an audit event.

        Args:
            event_type: Type of event
            severity: Event severity
            message: Human-readable message
            metadata: Additional event data
            user: User/agent identifier
        """
        event = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": event_type.value,
            "severity": severity.value,
            "message": message,
            "metadata": metadata or {},
            "user": user or "system",
        }

        # Write to file
        self._write_to_file(event)

        # Write to database if available
        if self.database:
            self._write_to_database(event)

    def _write_to_file(self, event: Dict[str, Any]) -> None:
        """Write audit event to file.

        Args:
            event: Event data
        """
        with open(self.log_file, "a") as f:
            f.write(json.dumps(event) + "\n")

    def _write_to_database(self, event: Dict[str, Any]) -> None:
        """Write audit event to database.

        Args:
            event: Event data
        """
        raise NotImplementedError("Database audit logging not yet implemented")

    async def log_transaction(
        self,
        tx_hash: str,
        operation: str,
        amount_usd: float,
        status: str,
        **kwargs: Any,
    ) -> None:
        """Log a transaction event.

        Args:
            tx_hash: Transaction hash
            operation: Operation type
            amount_usd: Transaction amount
            status: Transaction status
            **kwargs: Additional metadata
        """
        metadata = {
            "tx_hash": tx_hash,
            "operation": operation,
            "amount_usd": amount_usd,
            "status": status,
            **kwargs,
        }

        event_type = {
            "initiated": AuditEventType.TRANSACTION_INITIATED,
            "completed": AuditEventType.TRANSACTION_COMPLETED,
            "failed": AuditEventType.TRANSACTION_FAILED,
        }.get(status, AuditEventType.TRANSACTION_INITIATED)

        severity = (
            AuditSeverity.ERROR if status == "failed" else AuditSeverity.INFO
        )

        await self.log_event(
            event_type=event_type,
            severity=severity,
            message=f"Transaction {status}: {operation} for ${amount_usd}",
            metadata=metadata,
        )

    async def log_security_event(
        self,
        event_description: str,
        severity: AuditSeverity = AuditSeverity.WARNING,
        **metadata: Any,
    ) -> None:
        """Log a security-related event.

        Args:
            event_description: Description of security event
            severity: Event severity
            **metadata: Additional context
        """
        await self.log_event(
            event_type=AuditEventType.SECURITY_VIOLATION,
            severity=severity,
            message=event_description,
            metadata=metadata,
        )

    async def log_config_change(
        self,
        config_key: str,
        old_value: Any,
        new_value: Any,
        user: Optional[str] = None,
    ) -> None:
        """Log a configuration change.

        Args:
            config_key: Configuration key changed
            old_value: Previous value
            new_value: New value
            user: User making the change
        """
        await self.log_event(
            event_type=AuditEventType.CONFIG_CHANGED,
            severity=AuditSeverity.WARNING,
            message=f"Configuration changed: {config_key}",
            metadata={
                "config_key": config_key,
                "old_value": str(old_value),
                "new_value": str(new_value),
            },
            user=user,
        )

    # Sprint 4 Priority 2: RPC logging methods

    async def log_rpc_request(
        self,
        endpoint_provider: str,
        network: str,
        method: str,
        latency_ms: float,
        success: bool,
    ) -> None:
        """Log an RPC request for audit trail.

        SECURITY: Never logs full RPC URLs (they contain API keys).
        Only logs the provider name (alchemy/quicknode/public).

        Args:
            endpoint_provider: Provider name (NOT the URL)
            network: Network identifier
            method: RPC method called
            latency_ms: Request latency in milliseconds
            success: Whether request succeeded
        """
        await self.log_event(
            event_type=AuditEventType.RPC_REQUEST,
            severity=AuditSeverity.INFO if success else AuditSeverity.WARNING,
            message=f"RPC request to {endpoint_provider} on {network}",
            metadata={
                "endpoint": endpoint_provider,  # Provider name only, no URL!
                "network": network,
                "method": method,
                "latency_ms": round(latency_ms, 2),
                "success": success,
            },
        )

    async def log_rpc_usage_summary(self, summary: Dict[str, Any]) -> None:
        """Log daily RPC usage summary for cost monitoring.

        Args:
            summary: Usage summary dictionary from RpcUsageTracker
        """
        await self.log_event(
            event_type=AuditEventType.RPC_USAGE_SUMMARY,
            severity=AuditSeverity.INFO,
            message=f"Daily RPC usage: {summary.get('total_requests', 0)} requests",
            metadata=summary,
        )

    async def log_rpc_endpoint_failure(
        self,
        endpoint_provider: str,
        network: str,
        error: str,
        consecutive_failures: int,
    ) -> None:
        """Log RPC endpoint failure.

        Args:
            endpoint_provider: Provider name (NOT the URL)
            network: Network identifier
            error: Error message
            consecutive_failures: Count of consecutive failures
        """
        await self.log_event(
            event_type=AuditEventType.RPC_ENDPOINT_FAILURE,
            severity=AuditSeverity.WARNING,
            message=f"RPC endpoint {endpoint_provider} failing on {network}",
            metadata={
                "endpoint": endpoint_provider,
                "network": network,
                "error": error,
                "consecutive_failures": consecutive_failures,
            },
        )

    async def log_rpc_circuit_breaker_opened(
        self,
        endpoint_provider: str,
        network: str,
        failure_count: int,
    ) -> None:
        """Log circuit breaker opening for an RPC endpoint.

        Args:
            endpoint_provider: Provider name (NOT the URL)
            network: Network identifier
            failure_count: Number of failures that triggered circuit open
        """
        await self.log_event(
            event_type=AuditEventType.RPC_CIRCUIT_BREAKER_OPENED,
            severity=AuditSeverity.ERROR,
            message=f"Circuit breaker opened for {endpoint_provider} on {network}",
            metadata={
                "endpoint": endpoint_provider,
                "network": network,
                "failure_count": failure_count,
            },
        )
