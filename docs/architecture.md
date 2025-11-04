# MAMMON Architecture

## Overview

MAMMON is an autonomous AI agent for optimizing DeFi yields on Base network with x402 protocol integration for the agent economy.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    MAMMON Core System                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐     ┌──────────────┐     ┌────────────┐  │
│  │ Orchestrator │────▶│ Yield Scanner│────▶│ Protocol   │  │
│  │    Agent     │     │    Agent     │     │ Integrations│ │
│  └──────────────┘     └──────────────┘     └────────────┘  │
│         │                     │                             │
│         ▼                     ▼                             │
│  ┌──────────────┐     ┌──────────────┐                     │
│  │ Risk Assessor│     │   Executor   │                     │
│  │    Agent     │     │    Agent     │                     │
│  └──────────────┘     └──────────────┘                     │
│                              │                              │
└──────────────────────────────┼──────────────────────────────┘
                               │
                 ┌─────────────┴─────────────┐
                 │                           │
          ┌──────▼──────┐            ┌──────▼──────┐
          │  Blockchain  │            │  Security   │
          │  (CDP SDK)   │            │   Layer     │
          └──────────────┘            └─────────────┘
                 │
          ┌──────▼──────┐
          │ Base Network│
          └─────────────┘
```

## Component Responsibilities

### Orchestrator Agent
- Coordinates all other agents
- Manages optimization cycles
- Handles approval workflows
- Maintains agent state

### Yield Scanner Agent
- Monitors all protocol yields
- Identifies opportunities
- Compares current vs available yields

### Risk Assessor Agent
- Evaluates protocol risks
- Assesses rebalance risks
- Checks concentration risk

### Executor Agent
- Builds transactions
- Handles signing/submission
- Manages gas optimization
- Enforces spending limits

### Protocol Integrations
- Abstract interface for all protocols
- Protocol-specific implementations
- Unified data format

### Security Layer
- Spending limits
- Approval requirements
- Audit logging
- Input validation

## Data Flow

1. **Yield Discovery**: Scanner queries all protocols for current yields
2. **Analysis**: Orchestrator analyzes opportunities using Claude
3. **Risk Assessment**: Risk assessor evaluates proposed actions
4. **Decision**: Orchestrator decides on rebalancing
5. **Approval**: If required, request user approval
6. **Execution**: Executor builds and submits transaction
7. **Monitoring**: Monitor transaction confirmation
8. **Logging**: Record all events in database

## Technology Stack

- **LangGraph**: Agent orchestration
- **CDP SDK**: Blockchain interaction
- **Claude API**: AI decision-making
- **SQLAlchemy**: Data persistence
- **Streamlit**: Dashboard UI
- **Pydantic**: Configuration validation

## Security Architecture

### Defense in Depth
1. Configuration validation (never trust env vars)
2. Input validation (all external data)
3. Spending limits (multiple tiers)
4. Approval workflows (human oversight)
5. Audit logging (immutable trail)

### Fail-Safe Defaults
- Deny by default
- Require explicit approval for large amounts
- Rate limiting on all operations
- Graceful degradation on errors

## Future Architecture (x402)

### Phase 2: Client
- Service discovery
- Payment execution
- ROI tracking

### Phase 3: Server
- Service registration
- Payment verification
- Revenue tracking

## Database Schema

See `src/data/models.py` for complete schema.

Key tables:
- `positions`: Current positions
- `transactions`: Transaction history
- `decisions`: Agent decisions
- `performance_metrics`: Performance tracking
- `audit_logs`: Security audit trail

## Design Principles

1. **Security First**: Never compromise on safety
2. **Observability**: Log everything important
3. **Fail Gracefully**: Handle errors without losing funds
4. **Type Safety**: Full type hints everywhere
5. **Testability**: Easy to test all components
6. **Extensibility**: Easy to add new protocols/strategies
