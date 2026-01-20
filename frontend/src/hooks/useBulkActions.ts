import { useMutation, useQueryClient } from '@tanstack/react-query'
import { nodesApi } from '@/api'
import { nodeKeys } from './useNodes'
import { groupKeys } from './useGroups'
import { useSelectionStore } from '@/stores'

export function useBulkAssignGroup() {
  const queryClient = useQueryClient()
  const deselectAll = useSelectionStore((s) => s.deselectAll)

  return useMutation({
    mutationFn: ({ nodeIds, groupId }: { nodeIds: string[]; groupId: string | null }) =>
      nodesApi.bulkAssignGroup(nodeIds, groupId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: nodeKeys.lists() })
      queryClient.invalidateQueries({ queryKey: groupKeys.lists() })
      deselectAll()
    },
  })
}

export function useBulkAssignWorkflow() {
  const queryClient = useQueryClient()
  const deselectAll = useSelectionStore((s) => s.deselectAll)

  return useMutation({
    mutationFn: ({ nodeIds, workflowId }: { nodeIds: string[]; workflowId: string | null }) =>
      nodesApi.bulkAssignWorkflow(nodeIds, workflowId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: nodeKeys.lists() })
      deselectAll()
    },
  })
}

export function useBulkAddTag() {
  const queryClient = useQueryClient()
  const deselectAll = useSelectionStore((s) => s.deselectAll)

  return useMutation({
    mutationFn: ({ nodeIds, tag }: { nodeIds: string[]; tag: string }) =>
      nodesApi.bulkAddTag(nodeIds, tag),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: nodeKeys.lists() })
      deselectAll()
    },
  })
}

export function useBulkRemoveTag() {
  const queryClient = useQueryClient()
  const deselectAll = useSelectionStore((s) => s.deselectAll)

  return useMutation({
    mutationFn: ({ nodeIds, tag }: { nodeIds: string[]; tag: string }) =>
      nodesApi.bulkRemoveTag(nodeIds, tag),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: nodeKeys.lists() })
      deselectAll()
    },
  })
}

export function useBulkChangeState() {
  const queryClient = useQueryClient()
  const deselectAll = useSelectionStore((s) => s.deselectAll)

  return useMutation({
    mutationFn: ({ nodeIds, newState }: { nodeIds: string[]; newState: string }) =>
      nodesApi.bulkChangeState(nodeIds, newState),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: nodeKeys.lists() })
      queryClient.invalidateQueries({ queryKey: nodeKeys.stats() })
      deselectAll()
    },
  })
}
