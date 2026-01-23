import { useEffect, useRef, useCallback, useState } from 'react'
import { useAuthStore } from '@/stores'

export type WebSocketEvent =
  | { type: 'node.created'; data: { id: string; mac_address: string } }
  | { type: 'node.state_changed'; data: { id: string; old_state: string; new_state: string } }
  | { type: 'node.updated'; data: { id: string } }
  | { type: 'install.progress'; data: { node_id: string; progress: number } }
  | { type: 'approval.requested'; data: { id: string; action_type: string } }
  | { type: 'approval.resolved'; data: { id: string; status: 'approved' | 'rejected' } }
  | { type: 'pong' }

type EventHandler = (event: WebSocketEvent) => void

interface UseWebSocketOptions {
  onMessage?: EventHandler
  onConnect?: () => void
  onDisconnect?: () => void
  onError?: (error: Event) => void
  reconnectInterval?: number
  maxReconnectAttempts?: number
  /** Connect even without authentication (for anonymous access) */
  allowAnonymous?: boolean
}

interface UseWebSocketReturn {
  isConnected: boolean
  send: (message: unknown) => void
  reconnect: () => void
}

export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketReturn {
  const {
    onMessage,
    onConnect,
    onDisconnect,
    onError,
    reconnectInterval = 3000,
    maxReconnectAttempts = 10,
    allowAnonymous = true, // Allow anonymous connections by default
  } = options

  const { accessToken, isAuthenticated } = useAuthStore()
  const [isConnected, setIsConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  const connect = useCallback(() => {
    // Only require auth if allowAnonymous is false
    if (!allowAnonymous && (!isAuthenticated || !accessToken)) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    let wsUrl = `${protocol}//${window.location.host}/api/v1/ws`

    // Add token if available
    if (accessToken) {
      wsUrl += `?token=${accessToken}`
    }

    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      setIsConnected(true)
      reconnectAttemptsRef.current = 0
      onConnect?.()
    }

    ws.onclose = () => {
      setIsConnected(false)
      onDisconnect?.()

      // Attempt to reconnect
      if (reconnectAttemptsRef.current < maxReconnectAttempts) {
        reconnectTimeoutRef.current = setTimeout(() => {
          reconnectAttemptsRef.current++
          connect()
        }, reconnectInterval)
      }
    }

    ws.onerror = (error) => {
      onError?.(error)
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as WebSocketEvent
        onMessage?.(data)
      } catch {
        console.error('Failed to parse WebSocket message:', event.data)
      }
    }
  }, [isAuthenticated, accessToken, allowAnonymous, onConnect, onDisconnect, onError, onMessage, reconnectInterval, maxReconnectAttempts])

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
    }
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
  }, [])

  const send = useCallback((message: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message))
    }
  }, [])

  const reconnect = useCallback(() => {
    disconnect()
    reconnectAttemptsRef.current = 0
    connect()
  }, [connect, disconnect])

  useEffect(() => {
    connect()
    return () => disconnect()
  }, [connect, disconnect])

  return { isConnected, send, reconnect }
}
