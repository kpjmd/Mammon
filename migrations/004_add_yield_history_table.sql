-- Migration: Add yield history tracking table
-- Purpose: Store historical yield snapshots for trend analysis and rebalancing decisions
-- Phase: 3 Sprint 2
-- Date: 2025-11-15

CREATE TABLE IF NOT EXISTS yield_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Pool identification
    protocol TEXT NOT NULL,
    pool_id TEXT NOT NULL,
    pool_name TEXT NOT NULL,

    -- Yield metrics at snapshot time
    apy DECIMAL(10, 6) NOT NULL,
    borrow_apy DECIMAL(10, 6),
    tvl DECIMAL(20, 2) NOT NULL,
    utilization DECIMAL(5, 4),

    -- Token information
    tokens TEXT NOT NULL,  -- JSON array of token symbols

    -- Metadata
    snapshot_timestamp TIMESTAMP NOT NULL,
    metadata TEXT,  -- JSON for protocol-specific data

    -- Indexing
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for fast protocol lookups
CREATE INDEX IF NOT EXISTS idx_yield_history_protocol
ON yield_history(protocol);

-- Index for fast pool lookups
CREATE INDEX IF NOT EXISTS idx_yield_history_pool
ON yield_history(pool_id);

-- Index for time-series queries
CREATE INDEX IF NOT EXISTS idx_yield_history_timestamp
ON yield_history(snapshot_timestamp);

-- Composite index for protocol+pool time series
CREATE INDEX IF NOT EXISTS idx_yield_history_protocol_pool_time
ON yield_history(protocol, pool_id, snapshot_timestamp DESC);

-- Trigger to ensure snapshot_timestamp is immutable
CREATE TRIGGER IF NOT EXISTS yield_history_immutable_timestamp
BEFORE UPDATE ON yield_history
BEGIN
    SELECT RAISE(ABORT, 'Cannot modify snapshot_timestamp')
    WHERE NEW.snapshot_timestamp != OLD.snapshot_timestamp;
END;
