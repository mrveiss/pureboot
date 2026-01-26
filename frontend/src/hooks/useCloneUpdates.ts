import { useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useWebSocket, type WebSocketEvent } from './useWebSocket'
import { cloneSessionKeys } from './useCloneSessions'

export function useCloneUpdates() {
  const queryClient = useQueryClient()

  const handleMessage = useCallback((event: WebSocketEvent) => {
    switch (event.type) {
      case 'clone.started':
      case 'clone.source_ready':
      case 'clone.completed':
      case 'clone.failed':
      case 'clone.cancelled':
        // Invalidate both list and specific session
        queryClient.invalidateQueries({ queryKey: cloneSessionKeys.lists() })
        queryClient.invalidateQueries({
          queryKey: cloneSessionKeys.detail(event.data.session_id),
        })
        break

      case 'clone.progress':
        // Update cache directly for smoother progress updates
        queryClient.setQueryData(
          cloneSessionKeys.detail(event.data.session_id),
          (old: unknown) => {
            const oldData = old as { data?: Record<string, unknown> } | undefined
            if (!oldData?.data) return old
            return {
              ...oldData,
              data: {
                ...oldData.data,
                bytes_transferred: event.data.bytes_transferred,
                bytes_total: event.data.bytes_total,
                progress_percent: event.data.progress_percent,
                transfer_rate_bps: event.data.transfer_rate_bps,
                status: event.data.status === 'transferring' ? 'cloning' : oldData.data.status,
              },
            }
          }
        )
        // Also invalidate list to update progress there
        queryClient.invalidateQueries({ queryKey: cloneSessionKeys.lists() })
        break
    }
  }, [queryClient])

  const { isConnected, reconnect } = useWebSocket({
    onMessage: handleMessage,
    onConnect: () => {
      console.log('WebSocket connected - clone updates enabled')
    },
    onDisconnect: () => {
      console.log('WebSocket disconnected - clone updates paused')
    },
  })

  return { isConnected, reconnect }
}
