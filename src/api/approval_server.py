"""FastAPI approval server for warm wallet transactions.

This server provides a web interface for approving warm wallet transactions.
It integrates with ApprovalManager via shared in-memory state (MVP) or
Redis (production).

Security:
- Bearer token authentication required for all routes
- HTTPS recommended in production
- Audit logging for all approval actions
- Timeout tracking (24h default for warm wallet)

Routes:
- GET  /health              - Health check (no auth)
- GET  /approvals/pending   - List pending approvals
- GET  /approvals/{id}      - Get approval details
- POST /approvals/{id}/approve - Approve transaction
- POST /approvals/{id}/reject  - Reject transaction
- GET  /wallet/status       - Get wallet tier status

Usage:
    # Initialize server with global state
    from src.api.approval_server import initialize_server, app
    initialize_server(approval_manager, tier_status)

    # Run server
    uvicorn src.api.approval_server:app --host 0.0.0.0 --port 8080
"""

import os
from datetime import datetime, UTC
from decimal import Decimal
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from src.security.approval import ApprovalManager, ApprovalRequest, ApprovalStatus
from src.security.audit import AuditEventType, AuditLogger, AuditSeverity
from src.utils.logger import get_logger
from src.wallet.tiered_config import TierStatus, WalletTier

logger = get_logger(__name__)

# FastAPI app
app = FastAPI(
    title="MAMMON Approval Server",
    description="Web interface for approving warm wallet transactions",
    version="1.0.0",
)

# Security
security = HTTPBearer()

# Global state (initialized via initialize_server())
_approval_manager: Optional[ApprovalManager] = None
_tier_status: Optional[TierStatus] = None
_audit_logger: Optional[AuditLogger] = None


def get_api_token() -> str:
    """Get the API token from environment.

    Returns:
        API token string

    Raises:
        ValueError: If APPROVAL_API_TOKEN not set
    """
    token = os.getenv("APPROVAL_API_TOKEN")
    if not token:
        raise ValueError(
            "APPROVAL_API_TOKEN environment variable is required. "
            "Generate with: openssl rand -hex 32"
        )
    return token


# Pydantic models for API responses
class ApprovalResponse(BaseModel):
    """Response model for approval requests."""

    request_id: str
    transaction_type: str
    amount_usd: float
    from_protocol: Optional[str]
    to_protocol: str
    rationale: str
    status: str
    created_at: datetime
    expires_at: datetime
    gas_cost_usd: Optional[float] = None


class ApprovalActionRequest(BaseModel):
    """Request model for approve/reject actions."""

    reason: Optional[str] = None


class WalletStatusResponse(BaseModel):
    """Response model for wallet status."""

    tier: str
    is_paused: bool
    pause_reason: Optional[str] = None
    current_balance_usd: float
    daily_spent_usd: float
    weekly_spent_usd: float
    monthly_spent_usd: float
    transactions_today: int


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str
    timestamp: str
    approval_manager_ready: bool
    tier_status_ready: bool


# Authentication dependency
async def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """Verify bearer token authentication.

    Args:
        credentials: HTTP authorization credentials

    Returns:
        Valid token string

    Raises:
        HTTPException: If token is invalid
    """
    try:
        expected_token = get_api_token()
    except ValueError as e:
        logger.error(f"API token not configured: {e}")
        raise HTTPException(status_code=500, detail="Server configuration error")

    if credentials.credentials != expected_token:
        # Log unauthorized access attempt
        if _audit_logger:
            await _audit_logger.log_event(
                AuditEventType.SECURITY_VIOLATION,
                AuditSeverity.ERROR,
                "Unauthorized approval API access attempt",
                metadata={"token_prefix": credentials.credentials[:8] + "..."},
            )
        raise HTTPException(status_code=401, detail="Invalid authentication token")

    return credentials.credentials


# Dependency injection for global state
def get_approval_manager() -> ApprovalManager:
    """Get the global approval manager.

    Returns:
        ApprovalManager instance

    Raises:
        HTTPException: If not initialized
    """
    if _approval_manager is None:
        raise HTTPException(
            status_code=500,
            detail="Approval manager not initialized. Call initialize_server() first.",
        )
    return _approval_manager


def get_tier_status() -> TierStatus:
    """Get the global tier status.

    Returns:
        TierStatus instance

    Raises:
        HTTPException: If not initialized
    """
    if _tier_status is None:
        raise HTTPException(
            status_code=500,
            detail="Tier status not initialized. Call initialize_server() first.",
        )
    return _tier_status


# Helper function to convert ApprovalRequest to ApprovalResponse
def _to_approval_response(req: ApprovalRequest) -> ApprovalResponse:
    """Convert ApprovalRequest to API response model."""
    return ApprovalResponse(
        request_id=req.request_id,
        transaction_type=req.transaction_type,
        amount_usd=float(req.amount_usd),
        from_protocol=req.from_protocol,
        to_protocol=req.to_protocol,
        rationale=req.rationale,
        status=req.status.value,
        created_at=req.created_at,
        expires_at=req.expires_at,
        gas_cost_usd=float(req.gas_cost_usd) if req.gas_cost_usd else None,
    )


# Routes
@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint (no authentication required).

    Returns:
        Health status including component readiness
    """
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(UTC).isoformat(),
        approval_manager_ready=_approval_manager is not None,
        tier_status_ready=_tier_status is not None,
    )


@app.get("/approvals/pending", response_model=List[ApprovalResponse])
async def list_pending_approvals(
    _token: str = Depends(verify_token),
    manager: ApprovalManager = Depends(get_approval_manager),
) -> List[ApprovalResponse]:
    """List all pending approval requests.

    Returns:
        List of pending approval requests
    """
    pending = manager.get_pending_requests()
    logger.info(f"Listed {len(pending)} pending approvals")
    return [_to_approval_response(req) for req in pending]


@app.get("/approvals/{request_id}", response_model=ApprovalResponse)
async def get_approval(
    request_id: str,
    _token: str = Depends(verify_token),
    manager: ApprovalManager = Depends(get_approval_manager),
) -> ApprovalResponse:
    """Get details of a specific approval request.

    Args:
        request_id: The approval request ID

    Returns:
        Approval request details

    Raises:
        HTTPException: If request not found
    """
    if request_id not in manager.pending_requests:
        raise HTTPException(status_code=404, detail="Approval request not found")

    req = manager.pending_requests[request_id]
    return _to_approval_response(req)


@app.post("/approvals/{request_id}/approve")
async def approve_transaction(
    request_id: str,
    action: ApprovalActionRequest,
    _token: str = Depends(verify_token),
    manager: ApprovalManager = Depends(get_approval_manager),
) -> dict:
    """Approve a pending transaction.

    Args:
        request_id: The approval request ID
        action: Optional action details (reason)

    Returns:
        Approval confirmation

    Raises:
        HTTPException: If request not found or cannot be approved
    """
    success = manager.approve_request(request_id)

    if not success:
        raise HTTPException(
            status_code=400,
            detail="Cannot approve request (not found, expired, or already processed)",
        )

    # Audit log
    if _audit_logger:
        await _audit_logger.log_event(
            AuditEventType.TRANSACTION_APPROVED,
            AuditSeverity.WARNING,
            f"Transaction approved via API: {request_id}",
            metadata={"request_id": request_id, "reason": action.reason},
        )

    logger.info(f"Approved transaction: {request_id}")
    return {"status": "approved", "request_id": request_id}


@app.post("/approvals/{request_id}/reject")
async def reject_transaction(
    request_id: str,
    action: ApprovalActionRequest,
    _token: str = Depends(verify_token),
    manager: ApprovalManager = Depends(get_approval_manager),
) -> dict:
    """Reject a pending transaction.

    Args:
        request_id: The approval request ID
        action: Optional action details (reason)

    Returns:
        Rejection confirmation

    Raises:
        HTTPException: If request not found or cannot be rejected
    """
    success = manager.reject_request(request_id, action.reason or "Rejected via API")

    if not success:
        raise HTTPException(
            status_code=400,
            detail="Cannot reject request (not found or already processed)",
        )

    # Audit log
    if _audit_logger:
        await _audit_logger.log_event(
            AuditEventType.TRANSACTION_REJECTED,
            AuditSeverity.INFO,
            f"Transaction rejected via API: {request_id}",
            metadata={"request_id": request_id, "reason": action.reason},
        )

    logger.info(f"Rejected transaction: {request_id}")
    return {"status": "rejected", "request_id": request_id}


@app.get("/wallet/status", response_model=WalletStatusResponse)
async def get_wallet_status(
    _token: str = Depends(verify_token),
    status: TierStatus = Depends(get_tier_status),
) -> WalletStatusResponse:
    """Get current wallet tier status.

    Returns:
        Wallet status including spending and limits
    """
    return WalletStatusResponse(
        tier=status.tier.value,
        is_paused=status.is_paused,
        pause_reason=status.pause_reason,
        current_balance_usd=float(status.current_balance_usd),
        daily_spent_usd=float(status.daily_spent_usd),
        weekly_spent_usd=float(status.weekly_spent_usd),
        monthly_spent_usd=float(status.monthly_spent_usd),
        transactions_today=status.transactions_today,
    )


# Initialization function
def initialize_server(
    manager: ApprovalManager,
    status: TierStatus,
    audit_logger: Optional[AuditLogger] = None,
) -> None:
    """Initialize the approval server with global state.

    Must be called before starting the server.

    Args:
        manager: ApprovalManager instance for handling approvals
        status: TierStatus instance for wallet status
        audit_logger: Optional AuditLogger for security events
    """
    global _approval_manager, _tier_status, _audit_logger

    _approval_manager = manager
    _tier_status = status
    _audit_logger = audit_logger or AuditLogger()

    logger.info(
        f"Approval server initialized",
        extra={
            "tier": status.tier.value,
            "pending_approvals": len(manager.pending_requests),
        },
    )


def reset_server() -> None:
    """Reset server state (for testing).

    Clears all global state.
    """
    global _approval_manager, _tier_status, _audit_logger
    _approval_manager = None
    _tier_status = None
    _audit_logger = None
