import { useQuery } from '@tanstack/react-query'
import { workflowsApi } from '@/api'

export const workflowKeys = {
  all: ['workflows'] as const,
  lists: () => [...workflowKeys.all, 'list'] as const,
  details: () => [...workflowKeys.all, 'detail'] as const,
  detail: (id: string) => [...workflowKeys.details(), id] as const,
}

export function useWorkflows() {
  return useQuery({
    queryKey: workflowKeys.lists(),
    queryFn: () => workflowsApi.list(),
  })
}

export function useWorkflow(workflowId: string) {
  return useQuery({
    queryKey: workflowKeys.detail(workflowId),
    queryFn: () => workflowsApi.get(workflowId),
    enabled: !!workflowId,
  })
}
