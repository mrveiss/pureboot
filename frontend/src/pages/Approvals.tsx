import { useState, useMemo } from 'react'
import {
  useApprovals,
  useApprovalHistory,
  useMyPendingApprovals,
  useVote,
  useCancelApprovalById,
} from '../hooks/useApprovals'
import {
  ACTION_TYPE_LABELS,
  STATUS_LABELS,
  STATUS_COLORS,
  type Approval,
  type ApprovalVote,
} from '../types/approval'
import { useAuthStore } from '../stores/auth'

type TabType = 'my_pending' | 'all_pending' | 'resolved'

function formatDate(dateString: string): string {
  if (!dateString) return '-'
  const date = new Date(dateString)
  return date.toLocaleString()
}

function formatTimeRemaining(expiresAt: string | null): string {
  if (!expiresAt) return 'No expiration'
  const now = new Date()
  const expires = new Date(expiresAt)
  const diff = expires.getTime() - now.getTime()

  if (diff <= 0) return 'Expired'

  const days = Math.floor(diff / (1000 * 60 * 60 * 24))
  const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60))
  const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))

  if (days > 0) return `${days}d ${hours}h remaining`
  if (hours > 0) return `${hours}h ${minutes}m remaining`
  return `${minutes}m remaining`
}

interface VoteDialogProps {
  isOpen: boolean
  voteType: 'approve' | 'reject'
  onClose: () => void
  onSubmit: (comment: string) => void
  isLoading: boolean
}

function VoteDialog({ isOpen, voteType, onClose, onSubmit, isLoading }: VoteDialogProps) {
  const [comment, setComment] = useState('')

  if (!isOpen) return null

  const handleSubmit = () => {
    onSubmit(comment)
    setComment('')
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl p-6 w-full max-w-md">
        <h3 className="text-lg font-semibold mb-4">
          {voteType === 'approve' ? 'Approve Request' : 'Reject Request'}
        </h3>
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Comment (optional)
          </label>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Add a comment to explain your vote..."
            className="w-full px-3 py-2 border rounded-lg text-sm resize-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            rows={3}
          />
        </div>
        <div className="flex justify-end gap-3">
          <button
            onClick={onClose}
            disabled={isLoading}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={isLoading}
            className={`px-4 py-2 text-sm font-medium text-white rounded-lg disabled:opacity-50 ${
              voteType === 'approve'
                ? 'bg-green-600 hover:bg-green-700'
                : 'bg-red-600 hover:bg-red-700'
            }`}
          >
            {isLoading ? 'Submitting...' : voteType === 'approve' ? 'Approve' : 'Reject'}
          </button>
        </div>
      </div>
    </div>
  )
}

interface VoteHistoryProps {
  votes: ApprovalVote[]
}

function VoteHistory({ votes }: VoteHistoryProps) {
  if (votes.length === 0) {
    return (
      <div className="text-sm text-gray-500 italic">No votes yet</div>
    )
  }

  return (
    <div className="space-y-2">
      {votes.map((vote) => (
        <div
          key={vote.id}
          className="flex items-start gap-3 p-2 rounded bg-gray-50"
        >
          <div
            className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center ${
              vote.vote === 'approve'
                ? 'bg-green-100 text-green-600'
                : 'bg-red-100 text-red-600'
            }`}
          >
            {vote.vote === 'approve' ? (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            ) : (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            )}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-medium text-sm text-gray-900">{vote.username}</span>
              <span
                className={`px-1.5 py-0.5 rounded text-xs ${
                  vote.vote === 'approve'
                    ? 'bg-green-100 text-green-700'
                    : 'bg-red-100 text-red-700'
                }`}
              >
                {vote.vote === 'approve' ? 'Approved' : 'Rejected'}
              </span>
              {vote.is_escalation_vote && (
                <span className="px-1.5 py-0.5 rounded text-xs bg-orange-100 text-orange-700">
                  Escalation
                </span>
              )}
            </div>
            {vote.comment && (
              <p className="text-sm text-gray-600 mt-1">"{vote.comment}"</p>
            )}
            <p className="text-xs text-gray-400 mt-1">{formatDate(vote.created_at)}</p>
          </div>
        </div>
      ))}
    </div>
  )
}

interface ApprovalCardProps {
  approval: Approval
  currentUserId: string
  onVote: (approvalId: string, vote: 'approve' | 'reject') => void
  onCancel: (approvalId: string) => void
}

function ApprovalCard({ approval, currentUserId, onVote, onCancel }: ApprovalCardProps) {
  const [showDetails, setShowDetails] = useState(false)

  const isPending = approval.status === 'pending'
  const isRequester = approval.requester_id === currentUserId
  const hasVoted = approval.votes.some((v) => v.user_id === currentUserId)
  const canVote = isPending && !isRequester && !hasVoted

  const approveCount = approval.votes.filter((v) => v.vote === 'approve').length
  const rejectCount = approval.votes.filter((v) => v.vote === 'reject').length

  return (
    <div className="bg-white border rounded-lg shadow-sm overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b bg-gray-50">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span
                className={`px-2.5 py-1 rounded-full text-xs font-medium ${
                  STATUS_COLORS[approval.status] || 'bg-gray-100'
                }`}
              >
                {STATUS_LABELS[approval.status] || approval.status}
              </span>
              <span className="text-sm font-semibold text-gray-900">
                {ACTION_TYPE_LABELS[approval.operation_type] || approval.operation_type}
              </span>
              {approval.escalation_count > 0 && (
                <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-800">
                  Escalated {approval.escalation_count}x
                </span>
              )}
            </div>
            <h3 className="text-base font-medium text-gray-900 mt-2">
              {approval.description}
            </h3>
          </div>
        </div>
      </div>

      {/* Body */}
      <div className="p-4">
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-gray-500">Requested by:</span>
            <span className="ml-2 font-medium text-gray-900">
              {approval.requester_username || 'Unknown'}
            </span>
          </div>
          <div>
            <span className="text-gray-500">Target:</span>
            <span className="ml-2 font-medium text-gray-900">
              {approval.target_type}/{approval.target_id}
            </span>
          </div>
          <div>
            <span className="text-gray-500">Created:</span>
            <span className="ml-2 text-gray-900">{formatDate(approval.created_at)}</span>
          </div>
          {isPending && (
            <div>
              <span className="text-gray-500">Expires:</span>
              <span className={`ml-2 ${approval.expires_at && new Date(approval.expires_at) < new Date() ? 'text-red-600' : 'text-orange-600'}`}>
                {formatTimeRemaining(approval.expires_at)}
              </span>
            </div>
          )}
        </div>

        {/* Vote Progress */}
        <div className="mt-4 p-3 bg-gray-50 rounded-lg">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-gray-700">Voting Progress</span>
            <span className="text-sm">
              <span className="text-green-600 font-semibold">{approveCount}</span>
              <span className="text-gray-400"> / </span>
              <span className="text-gray-700 font-semibold">{approval.required_approvers}</span>
              <span className="text-gray-500 ml-1">required approvals</span>
            </span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className="bg-green-500 h-2 rounded-full transition-all"
              style={{ width: `${Math.min((approveCount / approval.required_approvers) * 100, 100)}%` }}
            />
          </div>
          {rejectCount > 0 && (
            <div className="text-xs text-red-600 mt-1">
              {rejectCount} rejection{rejectCount !== 1 ? 's' : ''}
            </div>
          )}
        </div>

        {/* Expandable Details */}
        <button
          onClick={() => setShowDetails(!showDetails)}
          className="mt-4 flex items-center text-sm text-blue-600 hover:text-blue-800"
        >
          <svg
            className={`w-4 h-4 mr-1 transition-transform ${showDetails ? 'rotate-90' : ''}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
          {showDetails ? 'Hide vote history' : 'Show vote history'}
        </button>

        {showDetails && (
          <div className="mt-4 pt-4 border-t">
            <h4 className="text-sm font-medium text-gray-700 mb-3">Vote History</h4>
            <VoteHistory votes={approval.votes} />

            {approval.metadata && Object.keys(approval.metadata).length > 0 && (
              <div className="mt-4">
                <h4 className="text-sm font-medium text-gray-700 mb-2">Additional Details</h4>
                <pre className="bg-gray-100 p-3 rounded text-xs overflow-auto max-h-32">
                  {JSON.stringify(approval.metadata, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Footer Actions */}
      {(canVote || (isPending && isRequester) || (isPending && hasVoted && !isRequester)) && (
        <div className="p-4 border-t bg-gray-50">
          {canVote && (
            <div className="flex gap-3">
              <button
                onClick={() => onVote(approval.id, 'approve')}
                className="flex-1 inline-flex items-center justify-center px-4 py-2 text-sm font-medium text-white bg-green-600 rounded-lg hover:bg-green-700 transition-colors"
              >
                <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5" />
                </svg>
                Approve
              </button>
              <button
                onClick={() => onVote(approval.id, 'reject')}
                className="flex-1 inline-flex items-center justify-center px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 transition-colors"
              >
                <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 14H5.236a2 2 0 01-1.789-2.894l3.5-7A2 2 0 018.736 3h4.018a2 2 0 01.485.06l3.76.94m-7 10v5a2 2 0 002 2h.096c.5 0 .905-.405.905-.904 0-.715.211-1.413.608-2.008L17 13V4m-7 10h2m5-10h2a2 2 0 012 2v6a2 2 0 01-2 2h-2.5" />
                </svg>
                Reject
              </button>
            </div>
          )}

          {isPending && isRequester && (
            <button
              onClick={() => onCancel(approval.id)}
              className="inline-flex items-center px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
              Cancel Request
            </button>
          )}

          {isPending && hasVoted && !isRequester && (
            <p className="text-sm text-gray-500 italic flex items-center">
              <svg className="w-4 h-4 mr-2 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              You have already voted on this request
            </p>
          )}
        </div>
      )}
    </div>
  )
}

function EmptyState({ tab }: { tab: TabType }) {
  const messages = {
    my_pending: {
      title: 'No approvals waiting for your vote',
      description: 'When you need to review and vote on approval requests, they will appear here.',
    },
    all_pending: {
      title: 'No pending approvals',
      description: 'All approval requests have been resolved. New requests will appear here.',
    },
    resolved: {
      title: 'No resolved approvals',
      description: 'Approved, rejected, and cancelled requests will appear here.',
    },
  }

  const { title, description } = messages[tab]

  return (
    <div className="text-center py-12">
      <svg
        className="mx-auto h-12 w-12 text-gray-400"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
        />
      </svg>
      <h3 className="mt-4 text-lg font-medium text-gray-900">{title}</h3>
      <p className="mt-2 text-sm text-gray-500">{description}</p>
    </div>
  )
}

export default function Approvals() {
  const [tab, setTab] = useState<TabType>('my_pending')
  const [voteDialog, setVoteDialog] = useState<{
    isOpen: boolean
    approvalId: string
    voteType: 'approve' | 'reject'
  }>({ isOpen: false, approvalId: '', voteType: 'approve' })

  // Get current user from auth store
  const user = useAuthStore((state) => state.user)
  const currentUserId = user?.id || ''

  // Queries
  const myPendingQuery = useMyPendingApprovals()
  const allPendingQuery = useApprovals({ status: 'pending' })
  const historyQuery = useApprovalHistory()

  // Mutations
  const voteMutation = useVote()
  const cancelMutation = useCancelApprovalById()

  // Compute approval lists
  const myPendingApprovals = useMemo(() => {
    const approvals = myPendingQuery.data || []
    // Filter to show only approvals where current user hasn't voted and isn't the requester
    return approvals.filter(
      (a) => !a.votes.some((v) => v.user_id === currentUserId) && a.requester_id !== currentUserId
    )
  }, [myPendingQuery.data, currentUserId])

  const allPendingApprovals = allPendingQuery.data?.data || []
  const resolvedApprovals = useMemo(() => {
    return (historyQuery.data?.data || []).filter(
      (a) => a.status !== 'pending'
    )
  }, [historyQuery.data?.data])

  const isLoading =
    (tab === 'my_pending' && myPendingQuery.isLoading) ||
    (tab === 'all_pending' && allPendingQuery.isLoading) ||
    (tab === 'resolved' && historyQuery.isLoading)

  const handleOpenVoteDialog = (approvalId: string, voteType: 'approve' | 'reject') => {
    setVoteDialog({ isOpen: true, approvalId, voteType })
  }

  const handleCloseVoteDialog = () => {
    setVoteDialog({ isOpen: false, approvalId: '', voteType: 'approve' })
  }

  const handleVote = (comment: string) => {
    voteMutation.mutate(
      {
        approvalId: voteDialog.approvalId,
        data: { vote: voteDialog.voteType, comment: comment || undefined },
      },
      {
        onSuccess: () => {
          handleCloseVoteDialog()
        },
      }
    )
  }

  const handleCancel = (approvalId: string) => {
    if (confirm('Are you sure you want to cancel this approval request?')) {
      cancelMutation.mutate(approvalId)
    }
  }

  const getCurrentApprovals = (): Approval[] => {
    switch (tab) {
      case 'my_pending':
        return myPendingApprovals
      case 'all_pending':
        return allPendingApprovals
      case 'resolved':
        return resolvedApprovals
      default:
        return []
    }
  }

  const approvals = getCurrentApprovals()

  const tabs = [
    {
      id: 'my_pending' as TabType,
      label: 'Pending My Vote',
      count: myPendingApprovals.length,
      countColor: 'bg-blue-100 text-blue-800',
    },
    {
      id: 'all_pending' as TabType,
      label: 'All Pending',
      count: allPendingApprovals.length,
      countColor: 'bg-yellow-100 text-yellow-800',
    },
    {
      id: 'resolved' as TabType,
      label: 'Resolved',
      count: null,
      countColor: '',
    },
  ]

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-gray-900">Approvals</h1>
        <p className="text-sm text-gray-500 mt-1">
          Four-eye principle: sensitive operations require multiple approvals before execution
        </p>
      </div>

      {/* Tabs */}
      <div className="border-b mb-6">
        <nav className="-mb-px flex gap-6">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`py-3 px-1 border-b-2 text-sm font-medium transition-colors ${
                tab === t.id
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              {t.label}
              {t.count !== null && t.count > 0 && (
                <span className={`ml-2 px-2 py-0.5 rounded-full text-xs font-medium ${t.countColor}`}>
                  {t.count}
                </span>
              )}
            </button>
          ))}
        </nav>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <span className="ml-3 text-gray-500">Loading approvals...</span>
        </div>
      ) : approvals.length === 0 ? (
        <EmptyState tab={tab} />
      ) : (
        <div className="space-y-4">
          {approvals.map((approval) => (
            <ApprovalCard
              key={approval.id}
              approval={approval}
              currentUserId={currentUserId}
              onVote={handleOpenVoteDialog}
              onCancel={handleCancel}
            />
          ))}
        </div>
      )}

      {/* Vote Dialog */}
      <VoteDialog
        isOpen={voteDialog.isOpen}
        voteType={voteDialog.voteType}
        onClose={handleCloseVoteDialog}
        onSubmit={handleVote}
        isLoading={voteMutation.isPending}
      />
    </div>
  )
}
