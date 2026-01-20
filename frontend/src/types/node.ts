export type NodeState =
  | 'discovered'
  | 'ignored'
  | 'pending'
  | 'installing'
  | 'installed'
  | 'active'
  | 'reprovision'
  | 'migrating'
  | 'retired'
  | 'decommissioned'
  | 'wiping'

export type Architecture = 'x86_64' | 'arm64'
export type BootMode = 'bios' | 'uefi'

export interface Node {
  id: string
  mac_address: string
  hostname: string | null
  ip_address: string | null
  state: NodeState
  workflow_id: string | null
  vendor: string | null
  model: string | null
  serial_number: string | null
  system_uuid: string | null
  arch: Architecture
  boot_mode: BootMode
  group_id: string | null
  tags: string[]
  created_at: string
  updated_at: string
  last_seen_at: string | null
}

export interface DeviceGroup {
  id: string
  name: string
  description: string | null
  default_workflow_id: string | null
  auto_provision: boolean
  created_at: string
  updated_at: string
  node_count: number
}

export const NODE_STATE_COLORS: Record<NodeState, string> = {
  discovered: 'bg-blue-500',
  ignored: 'bg-gray-500',
  pending: 'bg-yellow-500',
  installing: 'bg-orange-500',
  installed: 'bg-teal-500',
  active: 'bg-green-500',
  reprovision: 'bg-purple-500',
  migrating: 'bg-indigo-500',
  retired: 'bg-gray-600',
  decommissioned: 'bg-gray-700',
  wiping: 'bg-red-500',
}

export const NODE_STATE_LABELS: Record<NodeState, string> = {
  discovered: 'Discovered',
  ignored: 'Ignored',
  pending: 'Pending',
  installing: 'Installing',
  installed: 'Installed',
  active: 'Active',
  reprovision: 'Reprovision',
  migrating: 'Migrating',
  retired: 'Retired',
  decommissioned: 'Decommissioned',
  wiping: 'Wiping',
}

// Valid state transitions
export const NODE_STATE_TRANSITIONS: Record<NodeState, NodeState[]> = {
  discovered: ['pending', 'ignored'],
  ignored: ['discovered'],
  pending: ['installing'],
  installing: ['installed'],
  installed: ['active'],
  active: ['reprovision', 'migrating', 'retired'],
  reprovision: ['pending'],
  migrating: ['active'],
  retired: ['decommissioned'],
  decommissioned: ['wiping'],
  wiping: ['decommissioned'],
}

export interface StateHistoryEntry {
  id: string
  node_id: string
  from_state: NodeState | null
  to_state: NodeState
  changed_by: string
  changed_at: string
  comment: string | null
}

export interface NodeStats {
  total: number
  by_state: Record<NodeState, number>
  discovered_last_hour: number
  installing_count: number
}