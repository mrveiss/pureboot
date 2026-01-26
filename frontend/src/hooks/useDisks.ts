import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { disksApi } from '@/api/disks'
import type { PartitionOperationRequest } from '@/types/partition'

// Query keys for disk-related queries
export const diskKeys = {
  all: ['disks'] as const,
  node: (nodeId: string) => [...diskKeys.all, nodeId] as const,
  disk: (nodeId: string, device: string) => [...diskKeys.node(nodeId), device] as const,
  operations: (nodeId: string, device: string) => [...diskKeys.disk(nodeId, device), 'operations'] as const,
}

/**
 * Hook to list all disks for a node.
 * @param nodeId - The node ID to fetch disks for
 */
export function useNodeDisks(nodeId: string | undefined) {
  return useQuery({
    queryKey: diskKeys.node(nodeId!),
    queryFn: async () => {
      const response = await disksApi.listDisks(nodeId!)
      return response.data
    },
    enabled: !!nodeId,
    staleTime: 30_000, // 30 seconds
  })
}

/**
 * Hook to get a specific disk for a node.
 * @param nodeId - The node ID
 * @param device - The device path (e.g., /dev/sda)
 */
export function useNodeDisk(nodeId: string | undefined, device: string | undefined) {
  return useQuery({
    queryKey: diskKeys.disk(nodeId!, device!),
    queryFn: async () => {
      const response = await disksApi.getDisk(nodeId!, device!)
      return response.data
    },
    enabled: !!nodeId && !!device,
    staleTime: 30_000,
  })
}

/**
 * Hook to trigger a disk scan on a node.
 * Invalidates disk queries for the node on success.
 */
export function useTriggerDiskScan() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (nodeId: string) => disksApi.triggerScan(nodeId),
    onSuccess: (_, nodeId) => {
      // Invalidate disk queries for this node to trigger refetch
      queryClient.invalidateQueries({ queryKey: diskKeys.node(nodeId) })
    },
  })
}

/**
 * Hook to list partition operations for a specific disk.
 * @param nodeId - The node ID
 * @param device - The device path (e.g., /dev/sda)
 */
export function usePartitionOperations(nodeId: string | undefined, device: string | undefined) {
  return useQuery({
    queryKey: diskKeys.operations(nodeId!, device!),
    queryFn: async () => {
      const response = await disksApi.listOperations(nodeId!, device!)
      return response.data
    },
    enabled: !!nodeId && !!device,
    staleTime: 5_000, // 5 seconds - operations can change quickly
  })
}

/**
 * Hook to queue a partition operation.
 * Invalidates operation queries for the device on success.
 */
export function useQueueOperation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ nodeId, device, operation }: {
      nodeId: string
      device: string
      operation: PartitionOperationRequest
    }) => disksApi.queueOperation(nodeId, device, operation),
    onSuccess: (_, { nodeId, device }) => {
      queryClient.invalidateQueries({ queryKey: diskKeys.operations(nodeId, device) })
    },
  })
}

/**
 * Hook to remove a pending partition operation.
 * Invalidates operation queries for the device on success.
 */
export function useRemoveOperation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ nodeId, device, operationId }: {
      nodeId: string
      device: string
      operationId: string
    }) => disksApi.removeOperation(nodeId, device, operationId),
    onSuccess: (_, { nodeId, device }) => {
      queryClient.invalidateQueries({ queryKey: diskKeys.operations(nodeId, device) })
    },
  })
}

/**
 * Hook to apply all pending partition operations on a device.
 * Invalidates both operation and disk queries on success.
 */
export function useApplyOperations() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ nodeId, device }: { nodeId: string; device: string }) =>
      disksApi.applyOperations(nodeId, device),
    onSuccess: (_, { nodeId, device }) => {
      queryClient.invalidateQueries({ queryKey: diskKeys.operations(nodeId, device) })
      queryClient.invalidateQueries({ queryKey: diskKeys.disk(nodeId, device) })
    },
  })
}