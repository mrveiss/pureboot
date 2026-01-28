import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { sitesApi } from '@/api'
import type { Site, SiteCreate, SiteUpdate } from '@/types/site'

export const siteKeys = {
  all: ['sites'] as const,
  lists: () => [...siteKeys.all, 'list'] as const,
  list: (parentId?: string) => [...siteKeys.lists(), parentId] as const,
  details: () => [...siteKeys.all, 'detail'] as const,
  detail: (id: string) => [...siteKeys.details(), id] as const,
  nodes: (id: string) => [...siteKeys.all, 'nodes', id] as const,
  health: (id: string) => [...siteKeys.all, 'health', id] as const,
  conflicts: (id: string) => [...siteKeys.all, 'conflicts', id] as const,
}

export function useSites(parentId?: string) {
  return useQuery({
    queryKey: siteKeys.list(parentId),
    queryFn: () => sitesApi.list(parentId),
    refetchInterval: 30000,
    refetchIntervalInBackground: false,
  })
}

export function useSite(siteId: string) {
  return useQuery({
    queryKey: siteKeys.detail(siteId),
    queryFn: () => sitesApi.get(siteId),
    enabled: !!siteId,
    refetchInterval: 30000,
    refetchIntervalInBackground: false,
  })
}

export function useSiteNodes(siteId: string, includeDescendants?: boolean) {
  return useQuery({
    queryKey: siteKeys.nodes(siteId),
    queryFn: () => sitesApi.listNodes(siteId, includeDescendants),
    enabled: !!siteId,
  })
}

export function useSiteHealth(siteId: string) {
  return useQuery({
    queryKey: siteKeys.health(siteId),
    queryFn: () => sitesApi.getHealth(siteId),
    enabled: !!siteId,
    refetchInterval: 30000,
    refetchIntervalInBackground: false,
  })
}

export function useCreateSite() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: SiteCreate) => sitesApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: siteKeys.lists() })
    },
  })
}

export function useUpdateSite() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ siteId, data }: { siteId: string; data: SiteUpdate }) =>
      sitesApi.update(siteId, data),
    onSuccess: (_, { siteId }) => {
      queryClient.invalidateQueries({ queryKey: siteKeys.detail(siteId) })
      queryClient.invalidateQueries({ queryKey: siteKeys.lists() })
    },
  })
}

export function useDeleteSite() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (siteId: string) => sitesApi.delete(siteId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: siteKeys.lists() })
    },
  })
}

export function useTriggerSiteSync() {
  return useMutation({
    mutationFn: ({ siteId, fullSync }: { siteId: string; fullSync?: boolean }) =>
      sitesApi.triggerSync(siteId, fullSync),
  })
}

export function useGenerateAgentToken() {
  return useMutation({
    mutationFn: (siteId: string) => sitesApi.generateAgentToken(siteId),
  })
}
