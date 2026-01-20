import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { nodesApi } from '@/api'
import type { Node, NodeFilterParams, NodeState, NodeStats } from '@/types'

export const nodeKeys = {
  all: ['nodes'] as const,
  lists: () => [...nodeKeys.all, 'list'] as const,
  list: (filters: NodeFilterParams) => [...nodeKeys.lists(), filters] as const,
  details: () => [...nodeKeys.all, 'detail'] as const,
  detail: (id: string) => [...nodeKeys.details(), id] as const,
  stats: () => [...nodeKeys.all, 'stats'] as const,
  history: (id: string) => [...nodeKeys.all, 'history', id] as const,
}

export function useNodes(filters?: NodeFilterParams) {
  return useQuery({
    queryKey: nodeKeys.list(filters ?? {}),
    queryFn: () => nodesApi.list(filters),
  })
}

export function useNode(nodeId: string) {
  return useQuery({
    queryKey: nodeKeys.detail(nodeId),
    queryFn: () => nodesApi.get(nodeId),
    enabled: !!nodeId,
  })
}

export function useNodeStats() {
  return useQuery({
    queryKey: nodeKeys.stats(),
    queryFn: async (): Promise<NodeStats> => {
      // This will call a stats endpoint when available
      // For now, compute from list
      const response = await nodesApi.list({ limit: 1000 })
      const nodes = response.data

      const by_state = {} as Record<NodeState, number>
      const states: NodeState[] = [
        'discovered', 'ignored', 'pending', 'installing', 'installed',
        'active', 'reprovision', 'migrating', 'retired', 'decommissioned', 'wiping'
      ]
      states.forEach(s => by_state[s] = 0)
      nodes.forEach(n => by_state[n.state]++)

      const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString()
      const discovered_last_hour = nodes.filter(
        n => n.state === 'discovered' && n.created_at > oneHourAgo
      ).length

      return {
        total: nodes.length,
        by_state,
        discovered_last_hour,
        installing_count: by_state.installing,
      }
    },
    staleTime: 30000, // 30 seconds
  })
}

export function useUpdateNodeState() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ nodeId, newState }: { nodeId: string; newState: NodeState }) =>
      nodesApi.updateState(nodeId, newState),
    onSuccess: (_, { nodeId }) => {
      queryClient.invalidateQueries({ queryKey: nodeKeys.detail(nodeId) })
      queryClient.invalidateQueries({ queryKey: nodeKeys.lists() })
      queryClient.invalidateQueries({ queryKey: nodeKeys.stats() })
    },
  })
}

export function useUpdateNode() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ nodeId, data }: { nodeId: string; data: Partial<Node> }) =>
      nodesApi.update(nodeId, data),
    onSuccess: (_, { nodeId }) => {
      queryClient.invalidateQueries({ queryKey: nodeKeys.detail(nodeId) })
      queryClient.invalidateQueries({ queryKey: nodeKeys.lists() })
    },
  })
}
