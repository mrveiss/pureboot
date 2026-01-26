import { useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useWebSocket, type WebSocketEvent } from './useWebSocket'
import { diskKeys } from './useDisks'

/**
 * Extended WebSocket event types for partition operations.
 */
type PartitionWebSocketEvent =
  | WebSocketEvent
  | { type: 'partition.scan_complete'; data: { node_id: string } }
  | { type: 'partition.operation_queued'; data: { node_id: string; device: string; operation_id: string } }
  | { type: 'partition.operation_started'; data: { node_id: string; device: string; operation_id: string } }
  | { type: 'partition.operation_complete'; data: { node_id: string; device: string; operation_id: string } }
  | { type: 'partition.operation_failed'; data: { node_id: string; device: string; operation_id: string; error_message: string } }

/**
 * Hook to listen for partition-related WebSocket events and update React Query cache.
 * @param nodeId - The node ID to filter events for (optional)
 */
export function usePartitionUpdates(nodeId?: string | undefined) {
  const queryClient = useQueryClient()

  const handleMessage = useCallback((event: PartitionWebSocketEvent) => {
    // Filter by node ID if provided
    if (nodeId && 'data' in event && 'node_id' in event.data && event.data.node_id !== nodeId) {
      return
    }

    // Handle partition-specific events
    switch (event.type) {
      case 'partition.scan_complete': {
        // Disk scan completed - refresh disk list
        const scanEvent = event as { type: 'partition.scan_complete'; data: { node_id: string } }
        queryClient.invalidateQueries({ queryKey: diskKeys.node(scanEvent.data.node_id) })
        break
      }

      case 'partition.operation_queued':
      case 'partition.operation_started': {
        // Operation status changed - refresh operations list
        const opEvent = event as { type: string; data: { node_id: string; device: string; operation_id: string } }
        queryClient.invalidateQueries({
          queryKey: diskKeys.operations(opEvent.data.node_id, opEvent.data.device),
        })
        break
      }

      case 'partition.operation_complete': {
        // Operation completed - refresh operations list and disk data (partitions may have changed)
        const completeEvent = event as { type: 'partition.operation_complete'; data: { node_id: string; device: string; operation_id: string } }
        queryClient.invalidateQueries({
          queryKey: diskKeys.operations(completeEvent.data.node_id, completeEvent.data.device),
        })
        queryClient.invalidateQueries({
          queryKey: diskKeys.disk(completeEvent.data.node_id, completeEvent.data.device),
        })
        break
      }

      case 'partition.operation_failed': {
        // Operation failed - refresh operations list
        const failEvent = event as { type: 'partition.operation_failed'; data: { node_id: string; device: string; operation_id: string; error_message: string } }
        queryClient.invalidateQueries({
          queryKey: diskKeys.operations(failEvent.data.node_id, failEvent.data.device),
        })
        break
      }
    }
  }, [nodeId, queryClient])

  const { isConnected, reconnect } = useWebSocket({
    onMessage: handleMessage as (event: WebSocketEvent) => void,
    onConnect: () => {
      console.log('WebSocket connected - partition updates enabled')
    },
    onDisconnect: () => {
      console.log('WebSocket disconnected - partition updates paused')
    },
  })

  return { isConnected, reconnect }
}