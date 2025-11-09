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
        """
        self.request_id = request_id
        self.transaction_type = transaction_type
        self.amount_usd = amount_usd
        self.from_protocol = from_protocol
        self.to_protocol = to_protocol
        self.rationale = rationale
        self.status = ApprovalStatus.PENDING
        self.created_at = datetime.now()
        self.expires_at = self.created_at + timedelta(seconds=timeout_seconds)


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

    def requires_approval(self, amount_usd: Decimal) -> bool:
        """Check if amount requires manual approval.

        Args:
            amount_usd: Transaction amount in USD

        Returns:
            True if approval required
        """
        return amount_usd >= self.approval_threshold_usd

    async def request_approval(
        self,
        transaction_type: str,
        amount_usd: Decimal,
        from_protocol: Optional[str],
        to_protocol: str,
        rationale: str,
        timeout_seconds: int = 3600,
    ) -> ApprovalRequest:
        """Create an approval request.

        Args:
            transaction_type: Transaction type
            amount_usd: Amount in USD
            from_protocol: Source protocol
            to_protocol: Target protocol
            rationale: Explanation
            timeout_seconds: Request timeout in seconds (default: 1 hour)

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
        )

        # Store in pending requests
        self.pending_requests[request_id] = request

        return request

    async def wait_for_approval(
        self,
        request: ApprovalRequest,
        timeout_seconds: int = 3600,
        poll_interval: float = 0.5,
    ) -> ApprovalStatus:
        """Wait for user approval with timeout.

        Args:
            request: Approval request
            timeout_seconds: Maximum wait time
            poll_interval: How often to check status (seconds)

        Returns:
            Final approval status (APPROVED, REJECTED, or EXPIRED)
        """
        start_time = datetime.now()
        timeout = timedelta(seconds=timeout_seconds)

        # If callback is provided, call it immediately
        if self.approval_callback:
            try:
                approved = self.approval_callback(request)
                if approved:
                    request.status = ApprovalStatus.APPROVED
                    return ApprovalStatus.APPROVED
                else:
                    request.status = ApprovalStatus.REJECTED
                    return ApprovalStatus.REJECTED
            except Exception:
                # If callback fails, fall through to polling
                pass

        # Poll for approval status
        while True:
            # Check if request has been approved/rejected
            if request.status == ApprovalStatus.APPROVED:
                return ApprovalStatus.APPROVED
            elif request.status == ApprovalStatus.REJECTED:
                return ApprovalStatus.REJECTED

            # Check if expired
            elapsed = datetime.now() - start_time
            if elapsed >= timeout or datetime.now() >= request.expires_at:
                request.status = ApprovalStatus.EXPIRED
                return ApprovalStatus.EXPIRED

            # Wait before checking again
            await asyncio.sleep(poll_interval)

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
            request.status = ApprovalStatus.EXPIRED
            return False

        # Approve the request
        request.status = ApprovalStatus.APPROVED
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

        # Reject the request
        request.status = ApprovalStatus.REJECTED
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
