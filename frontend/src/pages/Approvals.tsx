import { useState } from 'react'
import {
  useApprovals,
  useApprovalHistory,
  useApproveRequest,
  useRejectRequest,
  useCancelApproval,
} from '../hooks/useApprovals'
import {
  ACTION_TYPE_LABELS,
  STATUS_LABELS,
  STATUS_COLORS,
  type Approval,
} from '../types/approval'

function formatDate(dateString: string): string {
  if (!dateString) return '-'
  const date = new Date(dateString)
  return date.toLocaleString()
}

function formatTimeRemaining(expiresAt: string): string {
  const now = new Date()
  const expires = new Date(expiresAt)
  const diff = expires.getTime() - now.getTime()

  if (diff <= 0) return 'Expired'

  const hours = Math.floor(diff / (1000 * 60 * 60))
  const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))

  if (hours > 0) return `${hours}h ${minutes}m remaining`
  return `${minutes}m remaining`
}

interface ApprovalCardProps {
  approval: Approval
  currentUser: string
  onApprove: (id: string, comment?: string) => void
  onReject: (id: string, comment?: string) => void
  onCancel: (id: string) => void
}

function ApprovalCard({ approval, currentUser, onApprove, onReject, onCancel }: ApprovalCardProps) {
  const [comment, setComment] = useState('')
  const [showDetails, setShowDetails] = useState(false)

  const isPending = approval.status === 'pending'
  const isRequester = approval.requester_name === currentUser
  const hasVoted = approval.votes.some((v) => v.user_name === currentUser)
  const canVote = isPending && !isRequester && !hasVoted

  return (
    <div className="bg-white border rounded-lg shadow-sm p-4 mb-4">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span
              className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLORS[approval.status] || 'bg-gray-100'}`}
            >
              {STATUS_LABELS[approval.status] || approval.status}
            </span>
            <span className="text-sm font-medium text-gray-900">
              {ACTION_TYPE_LABELS[approval.action_type] || approval.action_type}
            </span>
          </div>
          <p className="text-sm text-gray-600">
            Requested by <span className="font-medium">{approval.requester_name}</span>
            {' on '}
            {formatDate(approval.created_at)}
          </p>
          {isPending && (
            <p className="text-xs text-orange-600 mt-1">
              {formatTimeRemaining(approval.expires_at)}
            </p>
          )}
        </div>
        <div className="text-right">
          <div className="text-sm">
            <span className="text-green-600 font-medium">{approval.current_approvals}</span>
            {' / '}
            <span className="text-gray-500">{approval.required_approvers} approvals</span>
          </div>
          {approval.current_rejections > 0 && (
            <div className="text-xs text-red-600">
              {approval.current_rejections} rejection(s)
            </div>
          )}
        </div>
      </div>

      <button
        onClick={() => setShowDetails(!showDetails)}
        className="text-xs text-blue-600 hover:text-blue-800 mt-2"
      >
        {showDetails ? 'Hide details' : 'Show details'}
      </button>

      {showDetails && (
        <div className="mt-3 pt-3 border-t">
          <div className="text-xs text-gray-600 mb-2">Action Data:</div>
          <pre className="bg-gray-50 p-2 rounded text-xs overflow-auto max-h-32">
            {JSON.stringify(approval.action_data, null, 2)}
          </pre>

          {approval.votes.length > 0 && (
            <div className="mt-3">
              <div className="text-xs text-gray-600 mb-2">Votes:</div>
              <div className="space-y-1">
                {approval.votes.map((vote) => (
                  <div key={vote.id} className="flex items-center gap-2 text-xs">
                    <span
                      className={`w-16 px-1.5 py-0.5 rounded text-center ${
                        vote.vote === 'approve'
                          ? 'bg-green-100 text-green-700'
                          : 'bg-red-100 text-red-700'
                      }`}
                    >
                      {vote.vote}
                    </span>
                    <span className="font-medium">{vote.user_name}</span>
                    {vote.comment && (
                      <span className="text-gray-500">- {vote.comment}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {canVote && (
        <div className="mt-4 pt-3 border-t">
          <input
            type="text"
            placeholder="Optional comment..."
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            className="w-full px-3 py-1.5 text-sm border rounded mb-2"
          />
          <div className="flex gap-2">
            <button
              onClick={() => onApprove(approval.id, comment)}
              className="flex-1 px-3 py-1.5 text-sm font-medium text-white bg-green-600 rounded hover:bg-green-700"
            >
              Approve
            </button>
            <button
              onClick={() => onReject(approval.id, comment)}
              className="flex-1 px-3 py-1.5 text-sm font-medium text-white bg-red-600 rounded hover:bg-red-700"
            >
              Reject
            </button>
          </div>
        </div>
      )}

      {isPending && isRequester && (
        <div className="mt-4 pt-3 border-t">
          <button
            onClick={() => onCancel(approval.id)}
            className="px-3 py-1.5 text-sm font-medium text-gray-700 bg-gray-100 rounded hover:bg-gray-200"
          >
            Cancel Request
          </button>
        </div>
      )}

      {isPending && hasVoted && !isRequester && (
        <div className="mt-4 pt-3 border-t">
          <p className="text-sm text-gray-500 italic">You have already voted on this request</p>
        </div>
      )}
    </div>
  )
}

export default function Approvals() {
  const [tab, setTab] = useState<'pending' | 'history'>('pending')
  const [currentUser, setCurrentUser] = useState('admin') // TODO: Get from auth context

  const pendingQuery = useApprovals({ status: 'pending' })
  const historyQuery = useApprovalHistory()
  const approveRequest = useApproveRequest()
  const rejectRequest = useRejectRequest()
  const cancelApproval = useCancelApproval()

  const handleApprove = (id: string, comment?: string) => {
    approveRequest.mutate({
      id,
      data: { user_name: currentUser, comment: comment || undefined },
    })
  }

  const handleReject = (id: string, comment?: string) => {
    rejectRequest.mutate({
      id,
      data: { user_name: currentUser, comment: comment || undefined },
    })
  }

  const handleCancel = (id: string) => {
    cancelApproval.mutate({ id, requester_name: currentUser })
  }

  const pendingApprovals = pendingQuery.data?.data || []
  const historyApprovals = historyQuery.data?.data || []
  const isLoading = pendingQuery.isLoading || historyQuery.isLoading

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Approvals</h1>
          <p className="text-sm text-gray-500 mt-1">
            Four-eye principle: sensitive operations require multiple approvals
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-600">Acting as:</label>
          <input
            type="text"
            value={currentUser}
            onChange={(e) => setCurrentUser(e.target.value)}
            className="px-2 py-1 text-sm border rounded w-32"
          />
        </div>
      </div>

      <div className="border-b mb-4">
        <nav className="-mb-px flex gap-4">
          <button
            onClick={() => setTab('pending')}
            className={`py-2 px-1 border-b-2 text-sm font-medium ${
              tab === 'pending'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            Pending
            {pendingApprovals.length > 0 && (
              <span className="ml-2 bg-yellow-100 text-yellow-800 px-2 py-0.5 rounded-full text-xs">
                {pendingApprovals.length}
              </span>
            )}
          </button>
          <button
            onClick={() => setTab('history')}
            className={`py-2 px-1 border-b-2 text-sm font-medium ${
              tab === 'history'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            History
          </button>
        </nav>
      </div>

      {isLoading ? (
        <div className="text-center py-12 text-gray-500">Loading...</div>
      ) : tab === 'pending' ? (
        pendingApprovals.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <p>No pending approvals</p>
            <p className="text-sm mt-1">
              Approval requests will appear here when sensitive operations are initiated
            </p>
          </div>
        ) : (
          <div>
            {pendingApprovals.map((approval) => (
              <ApprovalCard
                key={approval.id}
                approval={approval}
                currentUser={currentUser}
                onApprove={handleApprove}
                onReject={handleReject}
                onCancel={handleCancel}
              />
            ))}
          </div>
        )
      ) : historyApprovals.length === 0 ? (
        <div className="text-center py-12 text-gray-500">No approval history</div>
      ) : (
        <div>
          {historyApprovals.map((approval) => (
            <ApprovalCard
              key={approval.id}
              approval={approval}
              currentUser={currentUser}
              onApprove={handleApprove}
              onReject={handleReject}
              onCancel={handleCancel}
            />
          ))}
        </div>
      )}
    </div>
  )
}
