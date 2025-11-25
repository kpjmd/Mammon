"""Transaction approval flow for manual authorization.

This module implements approval workflows requiring user confirmation
for transactions above configured thresholds.
"""

from typing import Any, Callable, Dict, Optional
from decimal import Decimal
from enum import Enum
from datetime import datetime, timedelta
import asyncio
import uuid


class ApprovalStatus(Enum):
    """Status of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ApprovalRequest:
    """Represents a transaction approval request.

    Attributes:
        request_id: Unique request identifier
        transaction_type: Type of transaction
        amount_usd: Transaction amount in USD
        from_protocol: Source protocol
        to_protocol: Target protocol
        rationale: Explanation for the transaction
        status: Current approval status
        created_at: Request creation time
        expires_at: Request expiration time
    """

    def __init__(
        self,
        request_id: str,
        transaction_type: str,
        amount_usd: Decimal,
        from_protocol: Optional[str],
        to_protocol: str,
        rationale: str,
        timeout_seconds: int = 3600,
        gas_estimate_wei: Optional[int] = None,
        gas_cost_usd: Optional[Decimal] = None,
        price_impact: Optional[Decimal] = None,
        slippage_bps: Optional[int] = None,
        expected_output: Optional[str] = None,
        min_output: Optional[str] = None,
    ) -> None:
        """Initialize an approval request.

        Args:
            request_id: Request identifier
            transaction_type: Transaction type
            amount_usd: Amount in USD
            from_protocol: Source protocol
            to_protocol: Target protocol
            rationale: Explanation
            timeout_seconds: Approval timeout
            gas_estimate_wei: Estimated gas in wei (optional)
            gas_cost_usd: Estimated gas cost in USD (optional)
            price_impact: Price impact percentage (optional, for swaps)
            slippage_bps: Slippage tolerance in basis points (optional, for swaps)
            expected_output: Expected output amount (optional, for swaps)
            min_output: Minimum output amount (optional, for swaps)
        """
        self.request_id = request_id
        self.transaction_type = transaction_type
        self.amount_usd = amount_usd
        self.from_protocol = from_protocol
        self.to_protocol = to_protocol
        self.rationale = rationale
        self.gas_estimate_wei = gas_estimate_wei
        self.gas_cost_usd = gas_cost_usd or Decimal("0")
        self.price_impact = price_impact
        self.slippage_bps = slippage_bps
        self.expected_output = expected_output
        self.min_output = min_output
        self.status = ApprovalStatus.PENDING
        self.created_at = datetime.now()
        self.expires_at = self.created_at + timedelta(seconds=timeout_seconds)

        # Event-driven status notification (non-blocking)
        self._status_changed = asyncio.Event()

    def _set_status(self, new_status: ApprovalStatus) -> None:
        """Update status and notify waiters (event-driven pattern).

        This method triggers the asyncio.Event, waking up any coroutines
        waiting in wait_for_approval() without polling.

        Args:
            new_status: New approval status
        """
        self.status = new_status
        self._status_changed.set()

    def get_display_message(self) -> str:
        """Get formatted approval request message for display.

        Returns:
            Formatted approval message with all relevant details
        """
        total_cost = self.amount_usd + self.gas_cost_usd

        message = f"""
╔══════════════════════════════════════════════════════════════
║ 🔐 APPROVAL REQUIRED
╠══════════════════════════════════════════════════════════════
║ Request ID: {self.request_id}
║ Type: {self.transaction_type}
║ From: {self.from_protocol or 'Wallet'}
║ To: {self.to_protocol}
║
║ Amount: ${self.amount_usd:,.2f}
║ Gas Cost: ${self.gas_cost_usd:,.2f}"""

        if self.gas_estimate_wei:
            message += f"""
║ Gas Estimate: {self.gas_estimate_wei:,} wei"""

        # Add swap-specific fields if present
        if self.expected_output and self.min_output:
            message += f"""
║
║ Swap Details:
║   Expected Output: {self.expected_output}
║   Minimum Output: {self.min_output}"""

        if self.slippage_bps is not None:
            slippage_percent = self.slippage_bps / 100
            message += f"""
║   Slippage Tolerance: {slippage_percent:.2f}%"""

        if self.price_impact is not None:
            message += f"""
║   Price Impact: {self.price_impact:.4f}%"""

        message += f"""
║ ─────────────────────────────────────────────────────────────
║ TOTAL COST: ${total_cost:,.2f}
║
║ Rationale: {self.rationale}
║
║ Expires: {self.expires_at.strftime('%Y-%m-%d %H:%M:%S')}
╚══════════════════════════════════════════════════════════════
"""
        return message


class ApprovalManager:
    """Manages transaction approval workflow.

    Handles approval requests, user interaction, and tracks
    approval history for audit purposes.

    Attributes:
        approval_threshold_usd: Threshold requiring approval
        pending_requests: Currently pending requests
        approval_callback: Function to call for approval UI
    """

    def __init__(
        self,
        approval_threshold_usd: Decimal,
        approval_callback: Optional[Callable[[ApprovalRequest], bool]] = None,
    ) -> None:
        """Initialize the approval manager.

        Args:
            approval_threshold_usd: Threshold requiring approval
            approval_callback: Optional callback for approval UI
        """
        self.approval_threshold_usd = approval_threshold_usd
        self.pending_requests: Dict[str, ApprovalRequest] = {}
        self.approval_callback = approval_callback

    def requires_approval(
        self,
        amount_usd: Decimal,
        gas_cost_usd: Optional[Decimal] = None,
    ) -> bool:
        """Check if amount requires manual approval.

        Args:
            amount_usd: Transaction amount in USD
            gas_cost_usd: Optional gas cost in USD (included in total)

        Returns:
            True if approval required
        """
        total_cost = amount_usd + (gas_cost_usd or Decimal("0"))
        return total_cost >= self.approval_threshold_usd

    async def request_approval(
        self,
        transaction_type: str,
        amount_usd: Decimal,
        from_protocol: Optional[str],
        to_protocol: str,
        rationale: str,
        timeout_seconds: int = 3600,
        gas_estimate_wei: Optional[int] = None,
        gas_cost_usd: Optional[Decimal] = None,
        price_impact: Optional[Decimal] = None,
        slippage_bps: Optional[int] = None,
        expected_output: Optional[str] = None,
        min_output: Optional[str] = None,
    ) -> ApprovalRequest:
        """Create an approval request.

        Args:
            transaction_type: Transaction type
            amount_usd: Amount in USD
            from_protocol: Source protocol
            to_protocol: Target protocol
            rationale: Explanation
            timeout_seconds: Request timeout in seconds (default: 1 hour)
            gas_estimate_wei: Estimated gas in wei (optional)
            gas_cost_usd: Estimated gas cost in USD (optional)
            price_impact: Price impact percentage (optional, for swaps)
            slippage_bps: Slippage tolerance in basis points (optional, for swaps)
            expected_output: Expected output amount (optional, for swaps)
            min_output: Minimum output amount (optional, for swaps)

        Returns:
            Approval request
        """
        # Generate unique request ID
        request_id = str(uuid.uuid4())

        # Create approval request
        request = ApprovalRequest(
            request_id=request_id,
            transaction_type=transaction_type,
            amount_usd=amount_usd,
            from_protocol=from_protocol,
            to_protocol=to_protocol,
            rationale=rationale,
            timeout_seconds=timeout_seconds,
            gas_estimate_wei=gas_estimate_wei,
            gas_cost_usd=gas_cost_usd,
            price_impact=price_impact,
            slippage_bps=slippage_bps,
            expected_output=expected_output,
            min_output=min_output,
        )

        # Store in pending requests
        self.pending_requests[request_id] = request

        return request

    async def wait_for_approval(
        self,
        request: ApprovalRequest,
        timeout_seconds: int = 3600,
    ) -> ApprovalStatus:
        """Wait for user approval using event-driven pattern (non-blocking).

        This method uses asyncio.Event instead of polling, providing instant
        response when approval status changes without blocking the event loop.

        Performance:
        - Old (polling): Check every 0.5s = 7200 checks/hour
        - New (event-driven): 1 event = instant response

        Args:
            request: Approval request
            timeout_seconds: Maximum wait time

        Returns:
            Final approval status (APPROVED, REJECTED, or EXPIRED)
        """
        # If callback is provided, call it immediately
        if self.approval_callback:
            try:
                approved = self.approval_callback(request)
                request._set_status(
                    ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
                )
                return request.status
            except Exception:
                # If callback fails, fall through to event waiting
                pass

        # Wait for status change event (non-blocking)
        try:
            await asyncio.wait_for(
                request._status_changed.wait(),
                timeout=timeout_seconds
            )
            return request.status
        except asyncio.TimeoutError:
            # Timeout expired - mark request as expired
            request._set_status(ApprovalStatus.EXPIRED)
            return ApprovalStatus.EXPIRED

    def approve_request(self, request_id: str) -> bool:
        """Approve a pending request.

        Args:
            request_id: Request to approve

        Returns:
            True if approved, False if not found
        """
        if request_id not in self.pending_requests:
            return False

        request = self.pending_requests[request_id]

        # Can only approve pending requests
        if request.status != ApprovalStatus.PENDING:
            return False

        # Check if expired
        if datetime.now() >= request.expires_at:
            request._set_status(ApprovalStatus.EXPIRED)
            return False

        # Approve the request (triggers event for wait_for_approval)
        request._set_status(ApprovalStatus.APPROVED)
        return True

    def reject_request(self, request_id: str, reason: str = "") -> bool:
        """Reject a pending request.

        Args:
            request_id: Request to reject
            reason: Optional rejection reason

        Returns:
            True if rejected, False if not found
        """
        if request_id not in self.pending_requests:
            return False

        request = self.pending_requests[request_id]

        # Can only reject pending requests
        if request.status != ApprovalStatus.PENDING:
            return False

        # Reject the request (triggers event for wait_for_approval)
        request._set_status(ApprovalStatus.REJECTED)
        return True

    def get_pending_requests(self) -> list[ApprovalRequest]:
        """Get all pending approval requests.

        Returns:
            List of pending requests
        """
        return [req for req in self.pending_requests.values() if req.status == ApprovalStatus.PENDING]


def cli_approval_callback(request: ApprovalRequest) -> bool:
    """Simple CLI approval callback for interactive terminal use.

    Prompts the user to approve or reject a transaction request.

    Args:
        request: Approval request to present

    Returns:
        True if approved, False if rejected

    Example:
        >>> manager = ApprovalManager(
        ...     approval_threshold_usd=Decimal("100"),
        ...     approval_callback=cli_approval_callback
        ... )
    """
    print("\n" + "=" * 60)
    print("⚠️  TRANSACTION APPROVAL REQUIRED")
    print("=" * 60)
    print(f"Type: {request.transaction_type}")
    print(f"Amount: ${request.amount_usd:.2f} USD")
    print(f"Protocol: {request.to_protocol}")
    if request.from_protocol:
        print(f"From Protocol: {request.from_protocol}")
    print(f"Rationale: {request.rationale}")
    print(f"Request ID: {request.request_id}")
    print("=" * 60)

    while True:
        response = input("Approve this transaction? [y/N]: ").strip().lower()
        if response in ('y', 'yes'):
            print("✅ Transaction APPROVED")
            return True
        elif response in ('n', 'no', ''):
            print("❌ Transaction REJECTED")
            return False
        else:
            print("Invalid input. Please enter 'y' or 'n'.")
