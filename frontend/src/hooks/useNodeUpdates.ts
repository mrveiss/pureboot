import { useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useWebSocket, type WebSocketEvent } from './useWebSocket'
import { nodeKeys } from './useNodes'

export function useNodeUpdates() {
  const queryClient = useQueryClient()

  const handleMessage = useCallback((event: WebSocketEvent) => {
    switch (event.type) {
      case 'node.created':
        // Invalidate node list to show new node
        queryClient.invalidateQueries({ queryKey: nodeKeys.lists() })
        queryClient.invalidateQueries({ queryKey: nodeKeys.stats() })
        break

      case 'node.state_changed':
        // Invalidate specific node and lists
        queryClient.invalidateQueries({ queryKey: nodeKeys.detail(event.data.id) })
        queryClient.invalidateQueries({ queryKey: nodeKeys.lists() })
        queryClient.invalidateQueries({ queryKey: nodeKeys.stats() })
        break

      case 'node.updated':
        // Invalidate specific node
        queryClient.invalidateQueries({ queryKey: nodeKeys.detail(event.data.id) })
        queryClient.invalidateQueries({ queryKey: nodeKeys.lists() })
        break
    }
  }, [queryClient])

  const { isConnected, reconnect } = useWebSocket({
    onMessage: handleMessage,
    onConnect: () => {
      console.log('WebSocket connected - real-time updates enabled')
    },
    onDisconnect: () => {
      console.log('WebSocket disconnected')
    },
  })

  return { isConnected, reconnect }
}
