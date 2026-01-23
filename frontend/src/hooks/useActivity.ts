import { useQuery } from '@tanstack/react-query'
import { activityApi } from '@/api'
import type { ActivityFilters } from '@/types'

export const activityKeys = {
  all: ['activity'] as const,
  lists: () => [...activityKeys.all, 'list'] as const,
  list: (filters: ActivityFilters) => [...activityKeys.lists(), filters] as const,
}

export function useActivity(filters?: ActivityFilters) {
  return useQuery({
    queryKey: activityKeys.list(filters ?? {}),
    queryFn: () => activityApi.list(filters),
    refetchInterval: 30000, // Refresh every 30 seconds
  })
}
