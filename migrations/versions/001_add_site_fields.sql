-- Migration: 001_add_site_fields
-- Date: 2026-01-26
-- Description: Add multi-site management fields for Phase 1
--
-- This migration adds:
-- 1. Site-specific fields to device_groups table
-- 2. home_site_id to nodes table
-- 3. sync_states table
-- 4. sync_conflicts table
-- 5. migration_claims table

-- ============================================
-- DeviceGroup site-specific fields
-- ============================================

-- Site flag
ALTER TABLE device_groups ADD COLUMN IF NOT EXISTS is_site BOOLEAN DEFAULT FALSE;

-- Site agent connection
ALTER TABLE device_groups ADD COLUMN IF NOT EXISTS agent_url VARCHAR(500);
ALTER TABLE device_groups ADD COLUMN IF NOT EXISTS agent_token_hash VARCHAR(64);
ALTER TABLE device_groups ADD COLUMN IF NOT EXISTS agent_status VARCHAR(20);
ALTER TABLE device_groups ADD COLUMN IF NOT EXISTS agent_last_seen TIMESTAMP;

-- Site autonomy settings
ALTER TABLE device_groups ADD COLUMN IF NOT EXISTS autonomy_level VARCHAR(20);
ALTER TABLE device_groups ADD COLUMN IF NOT EXISTS conflict_resolution VARCHAR(20);

-- Content caching policy
ALTER TABLE device_groups ADD COLUMN IF NOT EXISTS cache_policy VARCHAR(20);
ALTER TABLE device_groups ADD COLUMN IF NOT EXISTS cache_patterns_json TEXT;
ALTER TABLE device_groups ADD COLUMN IF NOT EXISTS cache_max_size_gb INTEGER;
ALTER TABLE device_groups ADD COLUMN IF NOT EXISTS cache_retention_days INTEGER;

-- Network discovery config
ALTER TABLE device_groups ADD COLUMN IF NOT EXISTS discovery_method VARCHAR(20);
ALTER TABLE device_groups ADD COLUMN IF NOT EXISTS discovery_config_json TEXT;

-- Migration policy
ALTER TABLE device_groups ADD COLUMN IF NOT EXISTS migration_policy VARCHAR(20);

-- Create index for site lookups
CREATE INDEX IF NOT EXISTS ix_device_groups_is_site ON device_groups (is_site);

-- ============================================
-- Node home_site_id field
-- ============================================

ALTER TABLE nodes ADD COLUMN IF NOT EXISTS home_site_id VARCHAR(36);

-- Add foreign key constraint (if not exists - PostgreSQL specific)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_nodes_home_site_id'
    ) THEN
        ALTER TABLE nodes ADD CONSTRAINT fk_nodes_home_site_id
        FOREIGN KEY (home_site_id) REFERENCES device_groups(id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_nodes_home_site_id ON nodes (home_site_id);

-- ============================================
-- SyncState table
-- ============================================

CREATE TABLE IF NOT EXISTS sync_states (
    id VARCHAR(36) PRIMARY KEY,
    entity_type VARCHAR(50) NOT NULL,
    entity_id VARCHAR(36) NOT NULL,
    site_id VARCHAR(36) NOT NULL REFERENCES device_groups(id),
    version INTEGER DEFAULT 1,
    last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_modified_by VARCHAR(50) NOT NULL,
    checksum VARCHAR(64),
    CONSTRAINT uq_sync_state_entity_site UNIQUE (entity_type, entity_id, site_id)
);

CREATE INDEX IF NOT EXISTS ix_sync_states_site_id ON sync_states (site_id);
CREATE INDEX IF NOT EXISTS ix_sync_states_entity ON sync_states (entity_type, entity_id);

-- ============================================
-- SyncConflict table
-- ============================================

CREATE TABLE IF NOT EXISTS sync_conflicts (
    id VARCHAR(36) PRIMARY KEY,
    entity_type VARCHAR(50) NOT NULL,
    entity_id VARCHAR(36) NOT NULL,
    site_id VARCHAR(36) NOT NULL REFERENCES device_groups(id),
    central_state_json TEXT NOT NULL,
    site_state_json TEXT NOT NULL,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    resolution VARCHAR(20)
);

CREATE INDEX IF NOT EXISTS ix_sync_conflicts_site_id ON sync_conflicts (site_id);
CREATE INDEX IF NOT EXISTS ix_sync_conflicts_unresolved ON sync_conflicts (site_id, resolved_at)
    WHERE resolved_at IS NULL;

-- ============================================
-- MigrationClaim table
-- ============================================

CREATE TABLE IF NOT EXISTS migration_claims (
    id VARCHAR(36) PRIMARY KEY,
    node_id VARCHAR(36) NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    source_site_id VARCHAR(36) NOT NULL REFERENCES device_groups(id),
    target_site_id VARCHAR(36) NOT NULL REFERENCES device_groups(id),
    status VARCHAR(20) DEFAULT 'pending',
    auto_approve_eligible BOOLEAN DEFAULT FALSE,
    policy_matched VARCHAR(50),
    approval_id VARCHAR(36),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    expires_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_migration_claims_node_id ON migration_claims (node_id);
CREATE INDEX IF NOT EXISTS ix_migration_claims_source_site ON migration_claims (source_site_id);
CREATE INDEX IF NOT EXISTS ix_migration_claims_target_site ON migration_claims (target_site_id);
CREATE INDEX IF NOT EXISTS ix_migration_claims_status ON migration_claims (status);

-- ============================================
-- Rollback script (for reference)
-- ============================================
--
-- DROP TABLE IF EXISTS migration_claims;
-- DROP TABLE IF EXISTS sync_conflicts;
-- DROP TABLE IF EXISTS sync_states;
--
-- ALTER TABLE nodes DROP CONSTRAINT IF EXISTS fk_nodes_home_site_id;
-- ALTER TABLE nodes DROP COLUMN IF EXISTS home_site_id;
--
-- ALTER TABLE device_groups DROP COLUMN IF EXISTS is_site;
-- ALTER TABLE device_groups DROP COLUMN IF EXISTS agent_url;
-- ALTER TABLE device_groups DROP COLUMN IF EXISTS agent_token_hash;
-- ALTER TABLE device_groups DROP COLUMN IF EXISTS agent_status;
-- ALTER TABLE device_groups DROP COLUMN IF EXISTS agent_last_seen;
-- ALTER TABLE device_groups DROP COLUMN IF EXISTS autonomy_level;
-- ALTER TABLE device_groups DROP COLUMN IF EXISTS conflict_resolution;
-- ALTER TABLE device_groups DROP COLUMN IF EXISTS cache_policy;
-- ALTER TABLE device_groups DROP COLUMN IF EXISTS cache_patterns_json;
-- ALTER TABLE device_groups DROP COLUMN IF EXISTS cache_max_size_gb;
-- ALTER TABLE device_groups DROP COLUMN IF EXISTS cache_retention_days;
-- ALTER TABLE device_groups DROP COLUMN IF EXISTS discovery_method;
-- ALTER TABLE device_groups DROP COLUMN IF EXISTS discovery_config_json;
-- ALTER TABLE device_groups DROP COLUMN IF EXISTS migration_policy;
