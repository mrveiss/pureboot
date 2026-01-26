export type CloneMode = 'staged' | 'direct'
export type CloneStatus = 'pending' | 'source_ready' | 'cloning' | 'completed' | 'failed' | 'cancelled'
export type ResizeMode = 'none' | 'shrink_source' | 'grow_target'
export type StagingStatus = 'pending' | 'provisioned' | 'uploading' | 'ready' | 'downloading' | 'cleanup' | 'deleted'

export interface CloneSession {
  id: string
  name: string | null
  status: CloneStatus
  clone_mode: CloneMode
  source_node_id: string
  source_node_name: string | null
  target_node_id: string | null
  target_node_name: string | null
  source_device: string
  target_device: string
  source_ip: string | null
  source_port: number
  staging_backend_id: string | null
  staging_backend_name: string | null
  staging_path: string | null
  staging_status: StagingStatus | null
  resize_mode: ResizeMode
  bytes_total: number | null
  bytes_transferred: number
  transfer_rate_bps: number | null
  progress_percent: number
  error_message: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  created_by: string | null
}

export interface CloneSessionCreate {
  name?: string
  source_node_id: string
  target_node_id?: string
  source_device?: string
  target_device?: string
  clone_mode?: CloneMode
  staging_backend_id?: string
  resize_mode?: ResizeMode
}

export interface CloneSessionUpdate {
  name?: string
  target_node_id?: string
  target_device?: string
  resize_mode?: ResizeMode
}

export const CLONE_STATUS_COLORS: Record<CloneStatus, string> = {
  pending: 'bg-gray-500',
  source_ready: 'bg-blue-500',
  cloning: 'bg-yellow-500',
  completed: 'bg-green-500',
  failed: 'bg-red-500',
  cancelled: 'bg-gray-400',
}

export const CLONE_STATUS_LABELS: Record<CloneStatus, string> = {
  pending: 'Pending',
  source_ready: 'Source Ready',
  cloning: 'Cloning',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
}
