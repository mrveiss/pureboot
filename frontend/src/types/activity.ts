export interface ActivityEntry {
  id: string
  timestamp: string
  type: 'state_change' | 'node_event'
  category: string
  node_id: string | null
  node_name: string | null
  message: string
  details: Record<string, unknown> | null
  triggered_by: string | null
}

export interface ActivityFilters {
  type?: 'state_change' | 'node_event'
  node_id?: string
  event_type?: string
  since?: string
  limit?: number
  offset?: number
}

export const ACTIVITY_TYPE_LABELS: Record<string, string> = {
  state_change: 'State Change',
  node_event: 'Node Event',
}

export const EVENT_TYPE_LABELS: Record<string, string> = {
  boot_started: 'Boot Started',
  install_started: 'Install Started',
  install_progress: 'Install Progress',
  install_complete: 'Install Complete',
  install_failed: 'Install Failed',
  first_boot: 'First Boot',
  heartbeat: 'Heartbeat',
  clone_source_ready: 'Clone Ready',
  deploy_complete: 'Deploy Complete',
}
