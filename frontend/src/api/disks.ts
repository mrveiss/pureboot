/**
 * Disk and partition management API client.
 */
import { apiClient } from './client'
import type { ApiResponse, ApiListResponse } from '@/types'
import type {
  Disk,
  PartitionOperation,
  PartitionOperationRequest,
  PartitionOperationListParams,
} from '@/types/partition'

/**
 * Response from disk scan trigger.
 */
export interface DiskScanTriggerResponse {
  node_id: string
  status: string
}

/**
 * Response from disk scan report.
 */
export interface DiskReportResponse {
  node_id: string
  disks_reported: number
  created: number
  updated: number
}

/**
 * Response from apply operations.
 */
export interface ApplyOperationsResponse {
  node_id: string
  device: string
  pending_count: number
  status: string
}

/**
 * Response from remove operation.
 */
export interface RemoveOperationResponse {
  operation_id: string
  removed: boolean
}

/**
 * Report data structure for disk scan.
 */
export interface DiskScanReportData {
  disks: Array<{
    device: string
    size_bytes: number
    model?: string
    serial?: string
    partition_table?: string
    partitions?: Array<{
      number: number
      start_bytes: number
      end_bytes: number
      size_bytes: number
      type?: string
      filesystem?: string
      label?: string
      flags?: string[]
      used_bytes?: number
      used_percent?: number
      can_shrink?: boolean
      min_size_bytes?: number
    }>
  }>
}

/**
 * API client for disk and partition operations.
 */
export const disksApi = {
  /**
   * List all disks for a node.
   * @param nodeId - The node ID
   * @returns List of disks with partition information
   */
  async listDisks(nodeId: string): Promise<ApiListResponse<Disk>> {
    return apiClient.get<ApiListResponse<Disk>>(`/nodes/${nodeId}/disks`)
  },

  /**
   * Get specific disk details for a node.
   * @param nodeId - The node ID
   * @param device - The device path (e.g., /dev/sda)
   * @returns Disk information with partitions
   */
  async getDisk(nodeId: string, device: string): Promise<ApiResponse<Disk>> {
    // URL encode the device path (e.g., /dev/sda -> %2Fdev%2Fsda)
    const encodedDevice = encodeURIComponent(device)
    return apiClient.get<ApiResponse<Disk>>(`/nodes/${nodeId}/disks/${encodedDevice}`)
  },

  /**
   * Trigger a disk scan on a node.
   * The node will pick this up on its next poll and report disk information.
   * @param nodeId - The node ID
   * @returns Scan request status
   */
  async triggerScan(nodeId: string): Promise<ApiResponse<DiskScanTriggerResponse>> {
    return apiClient.post<ApiResponse<DiskScanTriggerResponse>>(`/nodes/${nodeId}/disks/scan`)
  },

  /**
   * Submit a disk scan report from a node.
   * This is typically called by node agents, not the frontend.
   * @param nodeId - The node ID
   * @param report - The disk scan report data
   * @returns Report processing result
   */
  async submitReport(nodeId: string, report: DiskScanReportData): Promise<ApiResponse<DiskReportResponse>> {
    return apiClient.post<ApiResponse<DiskReportResponse>>(`/nodes/${nodeId}/disks/report`, report)
  },

  /**
   * Queue a partition operation for a device.
   * @param nodeId - The node ID
   * @param device - The device path (e.g., /dev/sda)
   * @param operation - The operation to queue
   * @returns The created operation
   */
  async queueOperation(
    nodeId: string,
    device: string,
    operation: PartitionOperationRequest
  ): Promise<ApiResponse<PartitionOperation>> {
    const encodedDevice = encodeURIComponent(device)
    return apiClient.post<ApiResponse<PartitionOperation>>(
      `/nodes/${nodeId}/disks/${encodedDevice}/operations`,
      operation
    )
  },

  /**
   * List queued partition operations for a device.
   * @param nodeId - The node ID
   * @param device - The device path (e.g., /dev/sda)
   * @param params - Optional filter parameters
   * @returns List of operations ordered by sequence
   */
  async listOperations(
    nodeId: string,
    device: string,
    params?: PartitionOperationListParams
  ): Promise<ApiListResponse<PartitionOperation>> {
    const encodedDevice = encodeURIComponent(device)
    const queryParams: Record<string, string> = {}
    if (params?.status) queryParams.status = params.status
    return apiClient.get<ApiListResponse<PartitionOperation>>(
      `/nodes/${nodeId}/disks/${encodedDevice}/operations`,
      queryParams
    )
  },

  /**
   * Remove a pending partition operation.
   * Only operations with status 'pending' can be removed.
   * @param nodeId - The node ID
   * @param device - The device path (e.g., /dev/sda)
   * @param operationId - The operation ID to remove
   */
  async removeOperation(
    nodeId: string,
    device: string,
    operationId: string
  ): Promise<ApiResponse<RemoveOperationResponse>> {
    const encodedDevice = encodeURIComponent(device)
    return apiClient.delete<ApiResponse<RemoveOperationResponse>>(
      `/nodes/${nodeId}/disks/${encodedDevice}/operations/${operationId}`
    )
  },

  /**
   * Apply all pending partition operations on a device.
   * This broadcasts an event that the node agent will pick up to execute
   * the queued operations.
   * @param nodeId - The node ID
   * @param device - The device path (e.g., /dev/sda)
   * @returns Apply request status
   */
  async applyOperations(
    nodeId: string,
    device: string
  ): Promise<ApiResponse<ApplyOperationsResponse>> {
    const encodedDevice = encodeURIComponent(device)
    return apiClient.post<ApiResponse<ApplyOperationsResponse>>(
      `/nodes/${nodeId}/disks/${encodedDevice}/apply`
    )
  },

  /**
   * Update the status of a partition operation.
   * This is typically called by node agents, not the frontend.
   * @param nodeId - The node ID
   * @param operationId - The operation ID
   * @param status - The new status
   * @param errorMessage - Optional error message for failed status
   */
  async updateOperationStatus(
    nodeId: string,
    operationId: string,
    status: 'running' | 'completed' | 'failed',
    errorMessage?: string
  ): Promise<ApiResponse<{ operation_id: string; status: string }>> {
    return apiClient.post<ApiResponse<{ operation_id: string; status: string }>>(
      `/nodes/${nodeId}/partition-operations/${operationId}/status`,
      { status, error_message: errorMessage }
    )
  },
}
