import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { approvalsApi, type ApprovalFilters } from '../api/approvals'
import type { ApprovalCreate, VoteCreate } from '../types/approval'

export const approvalKeys = {
  all: ['approvals'] as const,
  lists: () => [...approvalKeys.all, 'list'] as const,
  list: (filters?: ApprovalFilters) => [...approvalKeys.lists(), filters] as const,
  myPending: () => [...approvalKeys.all, 'myPending'] as const,
  history: () => [...approvalKeys.all, 'history'] as const,
  stats: () => [...approvalKeys.all, 'stats'] as const,
  details: () => [...approvalKeys.all, 'detail'] as const,
  detail: (id: string) => [...approvalKeys.details(), id] as const,
}

export function useApprovalStats() {
  return useQuery({
    queryKey: approvalKeys.stats(),
    queryFn: () => approvalsApi.getStats(),
    refetchInterval: 30000, // Refresh every 30s for badge updates
  })
}

export function useApprovals(filters?: ApprovalFilters) {
  return useQuery({
    queryKey: approvalKeys.list(filters),
    queryFn: () => approvalsApi.list(filters),
  })
}

export function useMyPendingApprovals() {
  return useQuery({
    queryKey: approvalKeys.myPending(),
    queryFn: () => approvalsApi.listMyPending(),
  })
}

export function useApprovalHistory(limit = 50, offset = 0) {
  return useQuery({
    queryKey: [...approvalKeys.history(), limit, offset],
    queryFn: () => approvalsApi.getHistory(limit, offset),
  })
}

export function useApproval(id: string) {
  return useQuery({
    queryKey: approvalKeys.detail(id),
    queryFn: () => approvalsApi.get(id),
    enabled: !!id,
  })
}

export function useCreateApproval() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: ApprovalCreate) => approvalsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: approvalKeys.all })
    },
  })
}

export function useApproveRequest() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: VoteCreate }) =>
      approvalsApi.approve(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: approvalKeys.all })
    },
  })
}

export function useRejectRequest() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: VoteCreate }) =>
      approvalsApi.reject(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: approvalKeys.all })
    },
  })
}

export function useCancelApproval() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, requester_name }: { id: string; requester_name: string }) =>
      approvalsApi.cancel(id, requester_name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: approvalKeys.all })
    },
  })
}

export function useVote() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ approvalId, data }: { approvalId: string; data: VoteCreate }) =>
      approvalsApi.vote(approvalId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: approvalKeys.all })
    },
  })
}

export function useCancelApprovalById() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (approvalId: string) => approvalsApi.cancelById(approvalId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: approvalKeys.all })
    },
  })
}
