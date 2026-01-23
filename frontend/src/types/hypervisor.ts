export interface Hypervisor {
  id: string
  name: string
  type: 'ovirt' | 'proxmox'
  api_url: string
  username: string | null
  verify_ssl: boolean
  status: 'online' | 'offline' | 'error' | 'unknown'
  last_error: string | null
  last_sync_at: string | null
  vm_count: number
  host_count: number
  created_at: string
  updated_at: string
}

export interface HypervisorCreate {
  name: string
  type: 'ovirt' | 'proxmox'
  api_url: string
  username?: string
  password?: string
  verify_ssl?: boolean
}

export interface HypervisorUpdate {
  name?: string
  api_url?: string
  username?: string
  password?: string
  verify_ssl?: boolean
}

export interface HypervisorTestResult {
  success: boolean
  message: string
  version: string | null
  vm_count: number | null
  host_count: number | null
}

export interface HypervisorVM {
  id: string
  name: string
  status: string
  cpu_cores: number | null
  memory_mb: number | null
  os_type: string | null
  ip_addresses: string[]
  host: string | null
}

export interface HypervisorTemplate {
  id: string
  name: string
  os_type: string | null
  cpu_cores: number | null
  memory_mb: number | null
}

export const HYPERVISOR_TYPE_LABELS: Record<string, string> = {
  ovirt: 'oVirt / RHV',
  proxmox: 'Proxmox VE',
}

export const HYPERVISOR_STATUS_COLORS: Record<string, string> = {
  online: 'bg-green-500',
  offline: 'bg-gray-500',
  error: 'bg-red-500',
  unknown: 'bg-yellow-500',
}
