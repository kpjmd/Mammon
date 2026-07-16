-- Migration: Add rebalance intents table
-- Purpose: Track multi-step rebalances so withdraw-succeeded/deposit-failed
--          ("stranded") runs are queryable and recoverable.
-- Phase: 5 (WS3 hardening)
-- Date: 2026-07-15

CREATE TABLE IF NOT EXISTS rebalance_intents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    from_protocol TEXT,             -- NULL for idle-capital deployment
    to_protocol TEXT NOT NULL,
    token TEXT NOT NULL,
    amount DECIMAL(36, 18) NOT NULL,

    -- in_progress | completed | failed | stranded | recovered
    status TEXT NOT NULL DEFAULT 'in_progress',
    last_step TEXT,                 -- RebalanceStep value last reached

    withdraw_tx_hash TEXT,
    deposit_tx_hash TEXT,
    error TEXT,
    alerted_at TIMESTAMP,           -- stranded-alert de-duplication

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Fast lookup of unresolved / stranded intents on each cycle.
CREATE INDEX IF NOT EXISTS idx_rebalance_intents_status
ON rebalance_intents(status);

CREATE INDEX IF NOT EXISTS idx_rebalance_intents_token_status
ON rebalance_intents(token, status);
