// Storage Backend Types
export type StorageBackendType = 'nfs' | 'iscsi' | 's3' | 'http'
export type StorageBackendStatus = 'online' | 'offline' | 'error'

export interface NfsConfig {
  server: string
  export_path: string
  mount_options?: string
  auth_method: 'none' | 'kerberos'
}

export interface IscsiTargetConfig {
  target: string
  port: number
  chap_enabled: boolean
}

export interface S3Config {
  endpoint: string
  bucket: string
  region?: string
  access_key_id: string
  secret_access_key?: string // Only for create/update, never returned
  cdn_enabled: boolean
  cdn_url?: string
}

export interface HttpConfig {
  base_url: string
  auth_method: 'none' | 'basic' | 'bearer'
  username?: string
  password?: string // Only for create/update
}

export type StorageBackendConfig = NfsConfig | IscsiTargetConfig | S3Config | HttpConfig

export interface StorageBackendStats {
  used_bytes: number
  total_bytes: number | null
  file_count: number
  template_count: number
}

export interface StorageBackend {
  id: string
  name: string
  type: StorageBackendType
  status: StorageBackendStatus
  config: StorageBackendConfig
  stats: StorageBackendStats
  created_at: string
  updated_at: string
}

// File Browser Types
export type FileType = 'file' | 'directory'

export interface StorageFile {
  name: string
  path: string
  type: FileType
  size: number | null
  mime_type?: string
  modified_at: string
  item_count?: number
}

// iSCSI LUN Types
export type LunPurpose = 'boot_from_san' | 'install_source' | 'auto_provision'
export type LunStatus = 'active' | 'ready' | 'error' | 'creating' | 'deleting'

export interface IscsiLun {
  id: string
  name: string
  size_gb: number
  target_id: string
  target_name: string
  iqn: string
  purpose: LunPurpose
  status: LunStatus
  assigned_node_id: string | null
  assigned_node_name: string | null
  chap_enabled: boolean
  created_at: string
  updated_at: string
}

// Sync Job Types
export type SyncSchedule = 'manual' | 'hourly' | 'daily' | 'weekly' | 'monthly'
export type SyncStatus = 'idle' | 'running' | 'synced' | 'failed'

export interface SyncJobRun {
  id: string
  started_at: string
  completed_at: string | null
  status: 'running' | 'success' | 'failed'
  files_synced: number
  bytes_transferred: number
  error?: string
}

export interface SyncJob {
  id: string
  name: string
  source_url: string
  destination_backend_id: string
  destination_backend_name: string
  destination_path: string
  include_pattern?: string
  exclude_pattern?: string
  schedule: SyncSchedule
  schedule_day?: number
  schedule_time?: string
  verify_checksums: boolean
  delete_removed: boolean
  keep_versions: number
  status: SyncStatus
  last_run_at: string | null
  last_error?: string
  next_run_at: string | null
  created_at: string
  updated_at: string
}

// Display helpers
export const STORAGE_BACKEND_TYPE_LABELS: Record<StorageBackendType, string> = {
  nfs: 'NFS',
  iscsi: 'iSCSI',
  s3: 'S3',
  http: 'HTTP',
}

export const STORAGE_STATUS_COLORS: Record<StorageBackendStatus, string> = {
  online: 'bg-green-500',
  offline: 'bg-gray-500',
  error: 'bg-red-500',
}

export const LUN_PURPOSE_LABELS: Record<LunPurpose, string> = {
  boot_from_san: 'Boot from SAN',
  install_source: 'Install Source',
  auto_provision: 'Auto-provision',
}

export const LUN_STATUS_COLORS: Record<LunStatus, string> = {
  active: 'bg-green-500',
  ready: 'bg-blue-500',
  error: 'bg-red-500',
  creating: 'bg-yellow-500',
  deleting: 'bg-orange-500',
}

export const SYNC_STATUS_COLORS: Record<SyncStatus, string> = {
  idle: 'bg-gray-500',
  running: 'bg-yellow-500',
  synced: 'bg-green-500',
  failed: 'bg-red-500',
}

export const SYNC_SCHEDULE_LABELS: Record<SyncSchedule, string> = {
  manual: 'Manual',
  hourly: 'Hourly',
  daily: 'Daily',
  weekly: 'Weekly',
  monthly: 'Monthly',
}
