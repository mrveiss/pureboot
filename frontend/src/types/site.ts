export type AgentStatus = 'online' | 'offline' | 'degraded' | null

export type AutonomyLevel = 'readonly' | 'limited' | 'full'

export type CachePolicy = 'minimal' | 'assigned' | 'mirror' | 'pattern'

export type ConflictResolution = 'central_wins' | 'last_write' | 'site_wins' | 'manual'

export type DiscoveryMethod = 'dhcp' | 'dns' | 'anycast' | 'fallback'

export type MigrationPolicy = 'manual' | 'auto_accept' | 'auto_release' | 'bidirectional'

export type ConflictType = 'state_mismatch' | 'missing_local' | 'missing_central'

export type ConflictResolutionAction = 'keep_local' | 'keep_central' | 'merge'

export interface Site {
  id: string
  name: string
  description: string | null
  parent_id: string | null
  path: string
  depth: number
  children_count: number
  default_workflow_id: string | null
  auto_provision: boolean
  effective_workflow_id: string | null
  effective_auto_provision: boolean
  node_count: number
  created_at: string
  updated_at: string

  // Site-specific
  is_site: boolean
  agent_url: string | null
  agent_status: AgentStatus
  agent_last_seen: string | null

  // Site autonomy
  autonomy_level: AutonomyLevel | null
  conflict_resolution: ConflictResolution | null

  // Cache settings
  cache_policy: CachePolicy | null
  cache_patterns_json: string | null
  cache_max_size_gb: number | null
  cache_retention_days: number | null

  // Network discovery
  discovery_method: DiscoveryMethod | null
  discovery_config_json: string | null

  // Migration
  migration_policy: MigrationPolicy | null
}

export interface SiteCreate {
  name: string
  description?: string | null
  parent_id?: string | null
  agent_url?: string | null
  autonomy_level?: AutonomyLevel
  conflict_resolution?: ConflictResolution
  cache_policy?: CachePolicy
  cache_patterns_json?: string | null
  cache_max_size_gb?: number | null
  cache_retention_days?: number
  discovery_method?: DiscoveryMethod
  discovery_config_json?: string | null
  migration_policy?: MigrationPolicy
}

export interface SiteUpdate {
  name?: string
  description?: string | null
  parent_id?: string | null
  agent_url?: string | null
  autonomy_level?: AutonomyLevel
  conflict_resolution?: ConflictResolution
  cache_policy?: CachePolicy
  cache_patterns_json?: string | null
  cache_max_size_gb?: number | null
  cache_retention_days?: number
  discovery_method?: DiscoveryMethod
  discovery_config_json?: string | null
  migration_policy?: MigrationPolicy
}

export interface SiteHealth {
  site_id: string
  agent_status: AgentStatus
  agent_last_seen: string | null
  pending_sync_items: number
  conflicts_pending: number
  nodes_count: number
  cache_used_gb: number | null
  cache_max_gb: number | null
}

export interface SiteSyncResponse {
  sync_id: string
  status: 'started' | 'queued'
  message: string
}

export interface AgentTokenResponse {
  token: string
  expires_in_hours: number
  message: string
}

export interface SiteConflict {
  id: string
  site_id: string
  node_mac: string
  node_id: string | null
  local_state: string
  central_state: string
  local_updated_at: string
  central_updated_at: string
  conflict_type: ConflictType
  detected_at: string
  resolved_at: string | null
  resolution: ConflictResolutionAction | null
  resolved_by: string | null
}

export type SiteStatusDisplay = 'online' | 'degraded' | 'offline' | 'unknown'

export function getSiteStatus(site: Site): SiteStatusDisplay {
  if (!site.agent_status) return 'unknown'
  return site.agent_status as SiteStatusDisplay
}

export const SITE_STATUS_COLORS: Record<SiteStatusDisplay, string> = {
  online: 'bg-green-500',
  degraded: 'bg-yellow-500',
  offline: 'bg-red-500',
  unknown: 'bg-gray-400',
}

export const SITE_STATUS_LABELS: Record<SiteStatusDisplay, string> = {
  online: 'Online',
  degraded: 'Degraded',
  offline: 'Offline',
  unknown: 'Unknown',
}

export const AUTONOMY_LEVEL_LABELS: Record<AutonomyLevel, string> = {
  readonly: 'Read Only',
  limited: 'Limited',
  full: 'Full',
}

export const CACHE_POLICY_LABELS: Record<CachePolicy, string> = {
  minimal: 'Minimal',
  assigned: 'Assigned',
  mirror: 'Mirror',
  pattern: 'Pattern',
}

export const CONFLICT_RESOLUTION_LABELS: Record<ConflictResolution, string> = {
  central_wins: 'Central Wins',
  last_write: 'Last Write Wins',
  site_wins: 'Site Wins',
  manual: 'Manual',
}

export const CONFLICT_TYPE_LABELS: Record<ConflictType, string> = {
  state_mismatch: 'State Mismatch',
  missing_local: 'Missing Local',
  missing_central: 'Missing Central',
}
