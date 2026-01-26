import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { cloneApi, CloneSessionListParams, SourceReadyData, ProgressData } from '@/api/clone'
import type { CloneSessionCreate, CloneSessionUpdate } from '@/types/clone'

export const cloneSessionKeys = {
  all: ['clone-sessions'] as const,
  lists: () => [...cloneSessionKeys.all, 'list'] as const,
  list: (filters: CloneSessionListParams) => [...cloneSessionKeys.lists(), filters] as const,
  details: () => [...cloneSessionKeys.all, 'detail'] as const,
  detail: (id: string) => [...cloneSessionKeys.details(), id] as const,
}

export function useCloneSessions(filters?: CloneSessionListParams) {
  return useQuery({
    queryKey: cloneSessionKeys.list(filters ?? {}),
    queryFn: () => cloneApi.list(filters),
  })
}

export function useCloneSession(sessionId: string) {
  return useQuery({
    queryKey: cloneSessionKeys.detail(sessionId),
    queryFn: () => cloneApi.get(sessionId),
    enabled: !!sessionId,
  })
}

export function useCreateCloneSession() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: CloneSessionCreate) => cloneApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloneSessionKeys.lists() })
    },
  })
}

export function useUpdateCloneSession() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ sessionId, data }: { sessionId: string; data: CloneSessionUpdate }) =>
      cloneApi.update(sessionId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: cloneSessionKeys.detail(variables.sessionId) })
      queryClient.invalidateQueries({ queryKey: cloneSessionKeys.lists() })
    },
  })
}

export function useDeleteCloneSession() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (sessionId: string) => cloneApi.delete(sessionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloneSessionKeys.lists() })
    },
  })
}

// Additional mutations for clone session lifecycle callbacks

export function useSourceReady() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ sessionId, data }: { sessionId: string; data: SourceReadyData }) =>
      cloneApi.sourceReady(sessionId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: cloneSessionKeys.detail(variables.sessionId) })
      queryClient.invalidateQueries({ queryKey: cloneSessionKeys.lists() })
    },
  })
}

export function useCloneProgress() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ sessionId, data }: { sessionId: string; data: ProgressData }) =>
      cloneApi.progress(sessionId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: cloneSessionKeys.detail(variables.sessionId) })
    },
  })
}

export function useCompleteClone() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (sessionId: string) => cloneApi.complete(sessionId),
    onSuccess: (_, sessionId) => {
      queryClient.invalidateQueries({ queryKey: cloneSessionKeys.detail(sessionId) })
      queryClient.invalidateQueries({ queryKey: cloneSessionKeys.lists() })
    },
  })
}

export function useFailClone() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ sessionId, error }: { sessionId: string; error: string }) =>
      cloneApi.failed(sessionId, error),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: cloneSessionKeys.detail(variables.sessionId) })
      queryClient.invalidateQueries({ queryKey: cloneSessionKeys.lists() })
    },
  })
}
