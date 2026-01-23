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
      const response = await nodesApi.stats()
      return response.data
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

export function useCreateNode() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: Partial<Node>) => nodesApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: nodeKeys.lists() })
      queryClient.invalidateQueries({ queryKey: nodeKeys.stats() })
    },
  })
}
