/**
 * Partition management types for disk and partition operations.
 */

// ============== Partition and Disk Types ==============

/**
 * Information about a single partition on a disk.
 */
export interface Partition {
  number: number
  start_bytes: number
  end_bytes: number
  size_bytes: number
  size_human: string
  type: string  // efi, linux, swap, ntfs, etc.
  filesystem: string | null
  label: string | null
  flags: string[]
  used_bytes: number | null
  used_percent: number | null
  can_shrink: boolean
  min_size_bytes: number | null
}

/**
 * Partition table type for a disk.
 */
export type PartitionTable = 'gpt' | 'msdos' | 'unknown'

/**
 * Disk information from a node scan.
 */
export interface Disk {
  id: string
  node_id: string
  device: string
  size_bytes: number
  size_human: string
  model: string | null
  serial: string | null
  partition_table: PartitionTable | null
  partitions: Partition[]
  scanned_at: string
}

/**
 * Disk report submitted by a node after scanning.
 */
export interface DiskReport {
  node_id: string
  disks: Disk[]
  reported_at: string
}

// ============== Partition Operation Types ==============

/**
 * Types of partition operations that can be performed.
 */
export type PartitionOperationType = 'resize' | 'create' | 'delete' | 'format' | 'move' | 'set_flag'

/**
 * Status of a partition operation.
 */
export type PartitionOperationStatus = 'pending' | 'running' | 'completed' | 'failed'

/**
 * Partition operation response from the API.
 */
export interface PartitionOperation {
  id: string
  node_id: string
  session_id: string | null
  device: string
  operation: PartitionOperationType
  params: Record<string, unknown>
  sequence: number
  status: PartitionOperationStatus
  error_message: string | null
  created_at: string
  executed_at: string | null
}

// ============== Operation-Specific Parameter Types ==============

/**
 * Parameters for resize operation.
 */
export interface ResizeOperationParams {
  partition_number: number
  new_size_bytes: number
}

/**
 * Parameters for create operation.
 */
export interface CreateOperationParams {
  start_bytes: number
  end_bytes: number
  filesystem: string
  label?: string
  type?: string
}

/**
 * Parameters for delete operation.
 */
export interface DeleteOperationParams {
  partition_number: number
}

/**
 * Parameters for format operation.
 */
export interface FormatOperationParams {
  partition_number: number
  filesystem: string
  label?: string
}

/**
 * Parameters for move operation.
 */
export interface MoveOperationParams {
  partition_number: number
  new_start_bytes: number
}

/**
 * Parameters for set_flag operation.
 */
export interface SetFlagOperationParams {
  partition_number: number
  flag: string
  state: boolean
}

// ============== Request Types ==============

/**
 * Request to create a resize operation.
 */
export interface ResizeOperationRequest {
  operation: 'resize'
  params: ResizeOperationParams
}

/**
 * Request to create a partition create operation.
 */
export interface CreateOperationRequest {
  operation: 'create'
  params: CreateOperationParams
}

/**
 * Request to create a delete operation.
 */
export interface DeleteOperationRequest {
  operation: 'delete'
  params: DeleteOperationParams
}

/**
 * Request to create a format operation.
 */
export interface FormatOperationRequest {
  operation: 'format'
  params: FormatOperationParams
}

/**
 * Request to create a move operation.
 */
export interface MoveOperationRequest {
  operation: 'move'
  params: MoveOperationParams
}

/**
 * Request to create a set_flag operation.
 */
export interface SetFlagOperationRequest {
  operation: 'set_flag'
  params: SetFlagOperationParams
}

/**
 * Union type for all partition operation requests.
 */
export type PartitionOperationRequest =
  | ResizeOperationRequest
  | CreateOperationRequest
  | DeleteOperationRequest
  | FormatOperationRequest
  | MoveOperationRequest
  | SetFlagOperationRequest

/**
 * Operation status update from a node.
 */
export interface OperationStatusUpdate {
  status: 'running' | 'completed' | 'failed'
  error_message?: string
}

// ============== Query Parameters ==============

/**
 * Parameters for listing partition operations.
 */
export interface PartitionOperationListParams {
  status?: PartitionOperationStatus
}

// ============== Constants ==============

/**
 * Status colors for partition operations.
 */
export const PARTITION_OPERATION_STATUS_COLORS: Record<PartitionOperationStatus, string> = {
  pending: 'bg-gray-500',
  running: 'bg-yellow-500',
  completed: 'bg-green-500',
  failed: 'bg-red-500',
}

/**
 * Status labels for partition operations.
 */
export const PARTITION_OPERATION_STATUS_LABELS: Record<PartitionOperationStatus, string> = {
  pending: 'Pending',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
}

/**
 * Operation type labels.
 */
export const PARTITION_OPERATION_TYPE_LABELS: Record<PartitionOperationType, string> = {
  resize: 'Resize',
  create: 'Create',
  delete: 'Delete',
  format: 'Format',
  move: 'Move',
  set_flag: 'Set Flag',
}

/**
 * Common filesystem types.
 */
export const FILESYSTEM_TYPES = [
  'ext4',
  'ext3',
  'ext2',
  'xfs',
  'btrfs',
  'ntfs',
  'fat32',
  'fat16',
  'swap',
  'linux-swap',
] as const

export type FilesystemType = typeof FILESYSTEM_TYPES[number]

/**
 * Common partition flags.
 */
export const PARTITION_FLAGS = [
  'boot',
  'esp',
  'lvm',
  'raid',
  'swap',
  'hidden',
  'msftdata',
  'bios_grub',
] as const

export type PartitionFlag = typeof PARTITION_FLAGS[number]
