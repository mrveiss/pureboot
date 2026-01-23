import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { templatesApi, type TemplateFilters, type TemplateCreate, type TemplateUpdate } from '@/api'

export const templateKeys = {
  all: ['templates'] as const,
  lists: () => [...templateKeys.all, 'list'] as const,
  list: (filters: TemplateFilters) => [...templateKeys.lists(), filters] as const,
  details: () => [...templateKeys.all, 'detail'] as const,
  detail: (id: string) => [...templateKeys.details(), id] as const,
}

export function useTemplates(filters?: TemplateFilters) {
  return useQuery({
    queryKey: templateKeys.list(filters ?? {}),
    queryFn: () => templatesApi.list(filters),
  })
}

export function useTemplate(templateId: string) {
  return useQuery({
    queryKey: templateKeys.detail(templateId),
    queryFn: () => templatesApi.get(templateId),
    enabled: !!templateId,
  })
}

export function useCreateTemplate() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: TemplateCreate) => templatesApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: templateKeys.lists() })
    },
  })
}

export function useUpdateTemplate() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ templateId, data }: { templateId: string; data: TemplateUpdate }) =>
      templatesApi.update(templateId, data),
    onSuccess: (_, { templateId }) => {
      queryClient.invalidateQueries({ queryKey: templateKeys.detail(templateId) })
      queryClient.invalidateQueries({ queryKey: templateKeys.lists() })
    },
  })
}

export function useDeleteTemplate() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (templateId: string) => templatesApi.delete(templateId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: templateKeys.lists() })
    },
  })
}
