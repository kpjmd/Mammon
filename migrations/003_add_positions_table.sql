-- Migration 003: Add positions table for protocol position tracking
-- Created: 2025-11-15
-- Phase 3 Sprint 1: Yield Optimization

-- Create positions table
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wallet_address TEXT NOT NULL,
    protocol TEXT NOT NULL,  -- 'morpho', 'aave', 'aerodrome', etc.
    pool_id TEXT NOT NULL,
    token TEXT NOT NULL,
    amount DECIMAL NOT NULL,
    value_usd DECIMAL,
    entry_apy DECIMAL,
    current_apy DECIMAL,
    opened_at TIMESTAMP NOT NULL,
    closed_at TIMESTAMP,
    status TEXT DEFAULT 'active',  -- 'active', 'closed'
    metadata TEXT,  -- JSON string for protocol-specific data
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_positions_wallet ON positions(wallet_address);
CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
CREATE INDEX IF NOT EXISTS idx_positions_protocol ON positions(protocol);
CREATE INDEX IF NOT EXISTS idx_positions_wallet_status ON positions(wallet_address, status);

-- Create trigger for updated_at timestamp
CREATE TRIGGER IF NOT EXISTS update_positions_timestamp
AFTER UPDATE ON positions
BEGIN
    UPDATE positions SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;
