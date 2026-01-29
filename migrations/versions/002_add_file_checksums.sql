-- Migration: 002_add_file_checksums
-- Date: 2026-01-28
-- Description: Add file checksum tracking and system settings for file management
--
-- This migration adds:
-- 1. file_checksums table for tracking file integrity
-- 2. system_settings table for key-value system configuration

-- ============================================
-- FileChecksum table
-- ============================================
-- Tracks SHA256 checksums of files in storage backends
-- for integrity verification and change detection

CREATE TABLE IF NOT EXISTS file_checksums (
    id VARCHAR(36) PRIMARY KEY,
    backend_id VARCHAR(36) NOT NULL REFERENCES storage_backends(id) ON DELETE CASCADE,
    file_path VARCHAR(500) NOT NULL,
    checksum_sha256 VARCHAR(64) NOT NULL,
    size_bytes BIGINT NOT NULL,
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_backend_file_path UNIQUE (backend_id, file_path)
);

-- Index for faster lookups by backend
CREATE INDEX IF NOT EXISTS ix_file_checksums_backend_id ON file_checksums (backend_id);

-- Index for checksum lookups (e.g., finding duplicates)
CREATE INDEX IF NOT EXISTS ix_file_checksums_checksum ON file_checksums (checksum_sha256);

-- ============================================
-- SystemSetting table
-- ============================================
-- Key-value store for system-wide configuration settings

CREATE TABLE IF NOT EXISTS system_settings (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- Rollback script (for reference)
-- ============================================
--
-- DROP INDEX IF EXISTS ix_file_checksums_checksum;
-- DROP INDEX IF EXISTS ix_file_checksums_backend_id;
-- DROP TABLE IF EXISTS file_checksums;
-- DROP TABLE IF EXISTS system_settings;
