import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { hypervisorsApi } from '@/api/hypervisors'
import type { HypervisorCreate, HypervisorUpdate } from '@/types'

export const hypervisorKeys = {
  all: ['hypervisors'] as const,
  lists: () => [...hypervisorKeys.all, 'list'] as const,
  list: () => [...hypervisorKeys.lists()] as const,
  details: () => [...hypervisorKeys.all, 'detail'] as const,
  detail: (id: string) => [...hypervisorKeys.details(), id] as const,
  vms: (id: string) => [...hypervisorKeys.all, id, 'vms'] as const,
  templates: (id: string) => [...hypervisorKeys.all, id, 'templates'] as const,
}

export function useHypervisors() {
  return useQuery({
    queryKey: hypervisorKeys.list(),
    queryFn: () => hypervisorsApi.list(),
  })
}

export function useHypervisor(hypervisorId: string) {
  return useQuery({
    queryKey: hypervisorKeys.detail(hypervisorId),
    queryFn: () => hypervisorsApi.get(hypervisorId),
    enabled: !!hypervisorId,
  })
}

export function useCreateHypervisor() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: HypervisorCreate) => hypervisorsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: hypervisorKeys.lists() })
    },
  })
}

export function useUpdateHypervisor() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ hypervisorId, data }: { hypervisorId: string; data: HypervisorUpdate }) =>
      hypervisorsApi.update(hypervisorId, data),
    onSuccess: (_, { hypervisorId }) => {
      queryClient.invalidateQueries({ queryKey: hypervisorKeys.lists() })
      queryClient.invalidateQueries({ queryKey: hypervisorKeys.detail(hypervisorId) })
    },
  })
}

export function useDeleteHypervisor() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (hypervisorId: string) => hypervisorsApi.delete(hypervisorId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: hypervisorKeys.lists() })
    },
  })
}

export function useTestHypervisor() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (hypervisorId: string) => hypervisorsApi.test(hypervisorId),
    onSuccess: (_, hypervisorId) => {
      queryClient.invalidateQueries({ queryKey: hypervisorKeys.lists() })
      queryClient.invalidateQueries({ queryKey: hypervisorKeys.detail(hypervisorId) })
    },
  })
}

export function useHypervisorVMs(hypervisorId: string) {
  return useQuery({
    queryKey: hypervisorKeys.vms(hypervisorId),
    queryFn: () => hypervisorsApi.listVMs(hypervisorId),
    enabled: !!hypervisorId,
  })
}

export function useHypervisorTemplates(hypervisorId: string) {
  return useQuery({
    queryKey: hypervisorKeys.templates(hypervisorId),
    queryFn: () => hypervisorsApi.listTemplates(hypervisorId),
    enabled: !!hypervisorId,
  })
}
