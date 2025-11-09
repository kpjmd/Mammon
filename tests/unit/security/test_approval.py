"""Unit tests for transaction approval workflow.

Tests the approval system added in Phase 1C Sprint 2.
"""

import pytest
import asyncio
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import MagicMock
from src.security.approval import (
    ApprovalStatus,
    ApprovalRequest,
    ApprovalManager,
    cli_approval_callback,
)


class TestApprovalStatus:
    """Test ApprovalStatus enum."""

    def test_approval_status_values(self):
        """Test that all approval status values are defined."""
        assert ApprovalStatus.PENDING.value == "pending"
        assert ApprovalStatus.APPROVED.value == "approved"
        assert ApprovalStatus.REJECTED.value == "rejected"
        assert ApprovalStatus.EXPIRED.value == "expired"

    def test_approval_status_comparison(self):
        """Test comparing approval statuses."""
        assert ApprovalStatus.PENDING == ApprovalStatus.PENDING
        assert ApprovalStatus.APPROVED != ApprovalStatus.REJECTED


class TestApprovalRequest:
    """Test ApprovalRequest class."""

    def test_approval_request_creation(self):
        """Test creating an approval request."""
        request = ApprovalRequest(
            request_id="test-123",
            transaction_type="transfer",
            amount_usd=Decimal("100.00"),
            from_protocol=None,
            to_protocol="base-sepolia",
            rationale="Test transfer",
            timeout_seconds=3600,
        )

        assert request.request_id == "test-123"
        assert request.transaction_type == "transfer"
        assert request.amount_usd == Decimal("100.00")
        assert request.from_protocol is None
        assert request.to_protocol == "base-sepolia"
        assert request.rationale == "Test transfer"
        assert request.status == ApprovalStatus.PENDING

    def test_approval_request_timestamps(self):
        """Test that timestamps are set correctly."""
        before = datetime.now()

        request = ApprovalRequest(
            request_id="test-123",
            transaction_type="transfer",
            amount_usd=Decimal("100.00"),
            from_protocol=None,
            to_protocol="base-sepolia",
            rationale="Test transfer",
            timeout_seconds=3600,
        )

        after = datetime.now()

        assert before <= request.created_at <= after
        expected_expiry = request.created_at + timedelta(seconds=3600)
        assert request.expires_at == expected_expiry

    def test_approval_request_default_timeout(self):
        """Test default timeout is 1 hour."""
        request = ApprovalRequest(
            request_id="test-123",
            transaction_type="transfer",
            amount_usd=Decimal("100.00"),
            from_protocol=None,
            to_protocol="base-sepolia",
            rationale="Test transfer",
        )

        time_diff = request.expires_at - request.created_at
        assert time_diff == timedelta(seconds=3600)

    def test_approval_request_custom_timeout(self):
        """Test custom timeout."""
        request = ApprovalRequest(
            request_id="test-123",
            transaction_type="transfer",
            amount_usd=Decimal("100.00"),
            from_protocol=None,
            to_protocol="base-sepolia",
            rationale="Test transfer",
            timeout_seconds=1800,  # 30 minutes
        )

        time_diff = request.expires_at - request.created_at
        assert time_diff == timedelta(seconds=1800)

    def test_approval_request_with_from_protocol(self):
        """Test approval request with source protocol."""
        request = ApprovalRequest(
            request_id="test-123",
            transaction_type="withdraw",
            amount_usd=Decimal("500.00"),
            from_protocol="aerodrome",
            to_protocol="base-sepolia",
            rationale="Withdraw from Aerodrome",
        )

        assert request.from_protocol == "aerodrome"


class TestApprovalManager:
    """Test ApprovalManager class."""

    def test_approval_manager_creation(self):
        """Test creating an approval manager."""
        manager = ApprovalManager(approval_threshold_usd=Decimal("100.00"))

        assert manager.approval_threshold_usd == Decimal("100.00")
        assert manager.pending_requests == {}
        assert manager.approval_callback is None

    def test_approval_manager_with_callback(self):
        """Test creating approval manager with callback."""
        callback = MagicMock()
        manager = ApprovalManager(
            approval_threshold_usd=Decimal("100.00"),
            approval_callback=callback,
        )

        assert manager.approval_callback is callback

    def test_requires_approval_below_threshold(self):
        """Test that amounts below threshold don't require approval."""
        manager = ApprovalManager(approval_threshold_usd=Decimal("100.00"))

        assert manager.requires_approval(Decimal("50.00")) is False
        assert manager.requires_approval(Decimal("99.99")) is False

    def test_requires_approval_at_threshold(self):
        """Test that amounts at threshold require approval."""
        manager = ApprovalManager(approval_threshold_usd=Decimal("100.00"))

        assert manager.requires_approval(Decimal("100.00")) is True

    def test_requires_approval_above_threshold(self):
        """Test that amounts above threshold require approval."""
        manager = ApprovalManager(approval_threshold_usd=Decimal("100.00"))

        assert manager.requires_approval(Decimal("100.01")) is True
        assert manager.requires_approval(Decimal("1000.00")) is True

    @pytest.mark.asyncio
    async def test_request_approval(self):
        """Test creating an approval request."""
        manager = ApprovalManager(approval_threshold_usd=Decimal("100.00"))

        request = await manager.request_approval(
            transaction_type="transfer",
            amount_usd=Decimal("200.00"),
            from_protocol=None,
            to_protocol="base-sepolia",
            rationale="Test transfer",
        )

        assert request is not None
        assert request.transaction_type == "transfer"
        assert request.amount_usd == Decimal("200.00")
        assert request.status == ApprovalStatus.PENDING
        assert request.request_id in manager.pending_requests

    @pytest.mark.asyncio
    async def test_request_approval_generates_unique_ids(self):
        """Test that each request gets a unique ID."""
        manager = ApprovalManager(approval_threshold_usd=Decimal("100.00"))

        request1 = await manager.request_approval(
            transaction_type="transfer",
            amount_usd=Decimal("200.00"),
            from_protocol=None,
            to_protocol="base-sepolia",
            rationale="Test 1",
        )

        request2 = await manager.request_approval(
            transaction_type="transfer",
            amount_usd=Decimal("200.00"),
            from_protocol=None,
            to_protocol="base-sepolia",
            rationale="Test 2",
        )

        assert request1.request_id != request2.request_id
        assert len(manager.pending_requests) == 2

    def test_approve_request_success(self):
        """Test approving a pending request."""
        manager = ApprovalManager(approval_threshold_usd=Decimal("100.00"))

        # Create request manually
        request = ApprovalRequest(
            request_id="test-123",
            transaction_type="transfer",
            amount_usd=Decimal("200.00"),
            from_protocol=None,
            to_protocol="base-sepolia",
            rationale="Test transfer",
        )
        manager.pending_requests[request.request_id] = request

        # Approve the request
        result = manager.approve_request("test-123")

        assert result is True
        assert request.status == ApprovalStatus.APPROVED

    def test_approve_request_not_found(self):
        """Test approving non-existent request."""
        manager = ApprovalManager(approval_threshold_usd=Decimal("100.00"))

        result = manager.approve_request("nonexistent")

        assert result is False

    def test_approve_request_already_approved(self):
        """Test approving an already-approved request."""
        manager = ApprovalManager(approval_threshold_usd=Decimal("100.00"))

        request = ApprovalRequest(
            request_id="test-123",
            transaction_type="transfer",
            amount_usd=Decimal("200.00"),
            from_protocol=None,
            to_protocol="base-sepolia",
            rationale="Test transfer",
        )
        request.status = ApprovalStatus.APPROVED
        manager.pending_requests[request.request_id] = request

        result = manager.approve_request("test-123")

        assert result is False

    def test_approve_request_expired(self):
        """Test approving an expired request."""
        manager = ApprovalManager(approval_threshold_usd=Decimal("100.00"))

        # Create an expired request
        request = ApprovalRequest(
            request_id="test-123",
            transaction_type="transfer",
            amount_usd=Decimal("200.00"),
            from_protocol=None,
            to_protocol="base-sepolia",
            rationale="Test transfer",
            timeout_seconds=0,  # Expires immediately
        )
        # Force expiration by setting past time
        request.expires_at = datetime.now() - timedelta(seconds=1)
        manager.pending_requests[request.request_id] = request

        result = manager.approve_request("test-123")

        assert result is False
        assert request.status == ApprovalStatus.EXPIRED

    def test_reject_request_success(self):
        """Test rejecting a pending request."""
        manager = ApprovalManager(approval_threshold_usd=Decimal("100.00"))

        request = ApprovalRequest(
            request_id="test-123",
            transaction_type="transfer",
            amount_usd=Decimal("200.00"),
            from_protocol=None,
            to_protocol="base-sepolia",
            rationale="Test transfer",
        )
        manager.pending_requests[request.request_id] = request

        result = manager.reject_request("test-123", reason="Not authorized")

        assert result is True
        assert request.status == ApprovalStatus.REJECTED

    def test_reject_request_not_found(self):
        """Test rejecting non-existent request."""
        manager = ApprovalManager(approval_threshold_usd=Decimal("100.00"))

        result = manager.reject_request("nonexistent")

        assert result is False

    def test_reject_request_already_approved(self):
        """Test rejecting an already-approved request."""
        manager = ApprovalManager(approval_threshold_usd=Decimal("100.00"))

        request = ApprovalRequest(
            request_id="test-123",
            transaction_type="transfer",
            amount_usd=Decimal("200.00"),
            from_protocol=None,
            to_protocol="base-sepolia",
            rationale="Test transfer",
        )
        request.status = ApprovalStatus.APPROVED
        manager.pending_requests[request.request_id] = request

        result = manager.reject_request("test-123")

        assert result is False
        assert request.status == ApprovalStatus.APPROVED  # Should not change

    def test_get_pending_requests_empty(self):
        """Test getting pending requests when there are none."""
        manager = ApprovalManager(approval_threshold_usd=Decimal("100.00"))

        pending = manager.get_pending_requests()

        assert pending == []

    def test_get_pending_requests_with_pending(self):
        """Test getting pending requests."""
        manager = ApprovalManager(approval_threshold_usd=Decimal("100.00"))

        # Add some requests
        request1 = ApprovalRequest(
            request_id="test-1",
            transaction_type="transfer",
            amount_usd=Decimal("200.00"),
            from_protocol=None,
            to_protocol="base-sepolia",
            rationale="Test 1",
        )
        request2 = ApprovalRequest(
            request_id="test-2",
            transaction_type="transfer",
            amount_usd=Decimal("300.00"),
            from_protocol=None,
            to_protocol="base-sepolia",
            rationale="Test 2",
        )
        manager.pending_requests["test-1"] = request1
        manager.pending_requests["test-2"] = request2

        pending = manager.get_pending_requests()

        assert len(pending) == 2
        assert request1 in pending
        assert request2 in pending

    def test_get_pending_requests_filters_non_pending(self):
        """Test that get_pending_requests filters out non-pending requests."""
        manager = ApprovalManager(approval_threshold_usd=Decimal("100.00"))

        # Add requests with different statuses
        pending_request = ApprovalRequest(
            request_id="test-1",
            transaction_type="transfer",
            amount_usd=Decimal("200.00"),
            from_protocol=None,
            to_protocol="base-sepolia",
            rationale="Pending",
        )

        approved_request = ApprovalRequest(
            request_id="test-2",
            transaction_type="transfer",
            amount_usd=Decimal("300.00"),
            from_protocol=None,
            to_protocol="base-sepolia",
            rationale="Approved",
        )
        approved_request.status = ApprovalStatus.APPROVED

        rejected_request = ApprovalRequest(
            request_id="test-3",
            transaction_type="transfer",
            amount_usd=Decimal("400.00"),
            from_protocol=None,
            to_protocol="base-sepolia",
            rationale="Rejected",
        )
        rejected_request.status = ApprovalStatus.REJECTED

        manager.pending_requests["test-1"] = pending_request
        manager.pending_requests["test-2"] = approved_request
        manager.pending_requests["test-3"] = rejected_request

        pending = manager.get_pending_requests()

        assert len(pending) == 1
        assert pending_request in pending
        assert approved_request not in pending
        assert rejected_request not in pending


class TestWaitForApproval:
    """Test wait_for_approval functionality."""

    @pytest.mark.asyncio
    async def test_wait_for_approval_with_callback_approved(self):
        """Test waiting for approval with callback that approves."""
        callback = MagicMock(return_value=True)
        manager = ApprovalManager(
            approval_threshold_usd=Decimal("100.00"),
            approval_callback=callback,
        )

        request = await manager.request_approval(
            transaction_type="transfer",
            amount_usd=Decimal("200.00"),
            from_protocol=None,
            to_protocol="base-sepolia",
            rationale="Test transfer",
        )

        status = await manager.wait_for_approval(request, timeout_seconds=5)

        assert status == ApprovalStatus.APPROVED
        assert request.status == ApprovalStatus.APPROVED
        callback.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_wait_for_approval_with_callback_rejected(self):
        """Test waiting for approval with callback that rejects."""
        callback = MagicMock(return_value=False)
        manager = ApprovalManager(
            approval_threshold_usd=Decimal("100.00"),
            approval_callback=callback,
        )

        request = await manager.request_approval(
            transaction_type="transfer",
            amount_usd=Decimal("200.00"),
            from_protocol=None,
            to_protocol="base-sepolia",
            rationale="Test transfer",
        )

        status = await manager.wait_for_approval(request, timeout_seconds=5)

        assert status == ApprovalStatus.REJECTED
        assert request.status == ApprovalStatus.REJECTED
        callback.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_wait_for_approval_timeout(self):
        """Test that wait_for_approval times out."""
        manager = ApprovalManager(approval_threshold_usd=Decimal("100.00"))

        request = await manager.request_approval(
            transaction_type="transfer",
            amount_usd=Decimal("200.00"),
            from_protocol=None,
            to_protocol="base-sepolia",
            rationale="Test transfer",
            timeout_seconds=1,  # Very short timeout
        )

        status = await manager.wait_for_approval(request, timeout_seconds=1, poll_interval=0.1)

        assert status == ApprovalStatus.EXPIRED
        assert request.status == ApprovalStatus.EXPIRED

    @pytest.mark.asyncio
    async def test_wait_for_approval_manual_approval(self):
        """Test waiting for manual approval."""
        manager = ApprovalManager(approval_threshold_usd=Decimal("100.00"))

        request = await manager.request_approval(
            transaction_type="transfer",
            amount_usd=Decimal("200.00"),
            from_protocol=None,
            to_protocol="base-sepolia",
            rationale="Test transfer",
        )

        # Simulate manual approval after short delay
        async def approve_after_delay():
            await asyncio.sleep(0.2)
            manager.approve_request(request.request_id)

        # Start approval task
        approval_task = asyncio.create_task(approve_after_delay())

        # Wait for approval
        status = await manager.wait_for_approval(request, timeout_seconds=5, poll_interval=0.1)

        await approval_task

        assert status == ApprovalStatus.APPROVED

    @pytest.mark.asyncio
    async def test_wait_for_approval_manual_rejection(self):
        """Test waiting for manual rejection."""
        manager = ApprovalManager(approval_threshold_usd=Decimal("100.00"))

        request = await manager.request_approval(
            transaction_type="transfer",
            amount_usd=Decimal("200.00"),
            from_protocol=None,
            to_protocol="base-sepolia",
            rationale="Test transfer",
        )

        # Simulate manual rejection after short delay
        async def reject_after_delay():
            await asyncio.sleep(0.2)
            manager.reject_request(request.request_id)

        # Start rejection task
        rejection_task = asyncio.create_task(reject_after_delay())

        # Wait for result
        status = await manager.wait_for_approval(request, timeout_seconds=5, poll_interval=0.1)

        await rejection_task

        assert status == ApprovalStatus.REJECTED


class TestCLIApprovalCallback:
    """Test CLI approval callback (note: these tests are tricky due to input())."""

    def test_cli_approval_callback_exists(self):
        """Test that CLI callback function exists."""
        assert cli_approval_callback is not None
        assert callable(cli_approval_callback)

    # Note: Testing cli_approval_callback fully requires mocking input()
    # which is complex. In real usage, this would be tested manually or
    # with integration tests using subprocess.


class TestApprovalWorkflowIntegration:
    """Integration tests for approval workflow."""

    @pytest.mark.asyncio
    async def test_full_approval_workflow(self):
        """Test complete approval workflow from request to approval."""
        # Create manager with auto-approve callback
        callback = MagicMock(return_value=True)
        manager = ApprovalManager(
            approval_threshold_usd=Decimal("100.00"),
            approval_callback=callback,
        )

        # Check if approval required
        amount = Decimal("200.00")
        assert manager.requires_approval(amount) is True

        # Request approval
        request = await manager.request_approval(
            transaction_type="transfer",
            amount_usd=amount,
            from_protocol=None,
            to_protocol="base-sepolia",
            rationale="Test transfer",
        )

        # Wait for approval
        status = await manager.wait_for_approval(request)

        # Verify approval
        assert status == ApprovalStatus.APPROVED
        assert request.status == ApprovalStatus.APPROVED

    @pytest.mark.asyncio
    async def test_no_approval_needed_for_small_amounts(self):
        """Test that small amounts don't require approval."""
        manager = ApprovalManager(approval_threshold_usd=Decimal("100.00"))

        amount = Decimal("50.00")
        assert manager.requires_approval(amount) is False

        # No approval request should be created
        # (in real usage, this would skip the approval flow entirely)

    @pytest.mark.asyncio
    async def test_multiple_concurrent_approvals(self):
        """Test handling multiple approval requests concurrently."""
        callback = MagicMock(return_value=True)
        manager = ApprovalManager(
            approval_threshold_usd=Decimal("100.00"),
            approval_callback=callback,
        )

        # Create multiple requests
        request1 = await manager.request_approval(
            transaction_type="transfer",
            amount_usd=Decimal("200.00"),
            from_protocol=None,
            to_protocol="base-sepolia",
            rationale="Test 1",
        )

        request2 = await manager.request_approval(
            transaction_type="transfer",
            amount_usd=Decimal("300.00"),
            from_protocol=None,
            to_protocol="base-sepolia",
            rationale="Test 2",
        )

        # Process both
        status1, status2 = await asyncio.gather(
            manager.wait_for_approval(request1, timeout_seconds=5),
            manager.wait_for_approval(request2, timeout_seconds=5),
        )

        assert status1 == ApprovalStatus.APPROVED
        assert status2 == ApprovalStatus.APPROVED
        assert len(manager.pending_requests) == 2


class TestEdgeCases:
    """Test edge cases in approval workflow."""

    def test_zero_threshold(self):
        """Test that zero threshold requires approval for any amount."""
        manager = ApprovalManager(approval_threshold_usd=Decimal("0.00"))

        assert manager.requires_approval(Decimal("0.01")) is True
        assert manager.requires_approval(Decimal("0.00")) is True

    def test_very_large_threshold(self):
        """Test very large approval threshold."""
        manager = ApprovalManager(approval_threshold_usd=Decimal("1000000.00"))

        assert manager.requires_approval(Decimal("999999.99")) is False
        assert manager.requires_approval(Decimal("1000000.00")) is True

    @pytest.mark.asyncio
    async def test_callback_exception_handling(self):
        """Test that exceptions in callback are handled gracefully."""
        def failing_callback(request):
            raise Exception("Callback failed")

        manager = ApprovalManager(
            approval_threshold_usd=Decimal("100.00"),
            approval_callback=failing_callback,
        )

        request = await manager.request_approval(
            transaction_type="transfer",
            amount_usd=Decimal("200.00"),
            from_protocol=None,
            to_protocol="base-sepolia",
            rationale="Test transfer",
            timeout_seconds=1,
        )

        # Should fall back to polling and eventually timeout
        status = await manager.wait_for_approval(request, timeout_seconds=1, poll_interval=0.1)

        assert status == ApprovalStatus.EXPIRED
