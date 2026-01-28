import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { sitesApi } from '@/api'
import { siteKeys } from './useSites'
import type { ConflictResolutionAction } from '@/types/site'

export const conflictKeys = {
  all: ['conflicts'] as const,
  list: (siteId: string) => [...conflictKeys.all, 'list', siteId] as const,
}

export function useSiteConflicts(siteId: string) {
  return useQuery({
    queryKey: conflictKeys.list(siteId),
    queryFn: () => sitesApi.listConflicts(siteId),
    enabled: !!siteId,
    refetchInterval: 60000,
    refetchIntervalInBackground: false,
  })
}

export function useResolveConflict() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      siteId,
      conflictId,
      resolution,
    }: {
      siteId: string
      conflictId: string
      resolution: ConflictResolutionAction
    }) => sitesApi.resolveConflict(siteId, conflictId, resolution),
    onSuccess: (_, { siteId }) => {
      queryClient.invalidateQueries({ queryKey: conflictKeys.list(siteId) })
      queryClient.invalidateQueries({ queryKey: siteKeys.health(siteId) })
    },
  })
}

export function useResolveAllConflicts() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      siteId,
      resolution,
    }: {
      siteId: string
      resolution: ConflictResolutionAction
    }) => sitesApi.resolveAllConflicts(siteId, resolution),
    onSuccess: (_, { siteId }) => {
      queryClient.invalidateQueries({ queryKey: conflictKeys.list(siteId) })
      queryClient.invalidateQueries({ queryKey: siteKeys.health(siteId) })
    },
  })
}
