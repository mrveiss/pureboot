/**
 * Component showing queued partition operations with management controls.
 */
import * as React from 'react'
import { Button } from '@/components/ui/button'
import type { PartitionOperation, PartitionOperationStatus } from '@/types/partition'
import {
  PARTITION_OPERATION_TYPE_LABELS,
  PARTITION_OPERATION_STATUS_LABELS,
} from '@/types/partition'

interface OperationQueueProps {
  operations: PartitionOperation[]
  onRemove: (operationId: string) => void
  onApplyAll: () => void
  isApplying?: boolean
}

// Status colors for badges
const STATUS_COLORS: Record<PartitionOperationStatus, string> = {
  pending: 'bg-gray-100 text-gray-800 border-gray-200',
  running: 'bg-yellow-100 text-yellow-800 border-yellow-200',
  completed: 'bg-green-100 text-green-800 border-green-200',
  failed: 'bg-red-100 text-red-800 border-red-200',
}

// Operation type icons (using simple SVG shapes)
const OPERATION_ICONS: Record<string, React.ReactNode> = {
  resize: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
    </svg>
  ),
  create: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
    </svg>
  ),
  delete: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
    </svg>
  ),
  format: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
    </svg>
  ),
  move: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
    </svg>
  ),
  set_flag: (
    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 21v-4m0 0V5a2 2 0 012-2h6.5l1 1H21l-3 6 3 6h-8.5l-1-1H5a2 2 0 00-2 2zm9-13.5V9" />
    </svg>
  ),
}

function formatSize(bytes: number): string {
  if (bytes >= 1024 ** 4) return `${(bytes / 1024 ** 4).toFixed(2)} TB`
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(2)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(2)} KB`
  return `${bytes} B`
}

function getOperationDescription(operation: PartitionOperation): string {
  const params = operation.params as Record<string, unknown>

  switch (operation.operation) {
    case 'resize':
      return `Resize partition ${params.partition} to ${formatSize(params.new_size_bytes as number)}`
    case 'create':
      return `Create ${params.filesystem} partition (${formatSize((params.end_bytes as number) - (params.start_bytes as number))})`
    case 'delete':
      return `Delete partition ${params.partition}`
    case 'format':
      return `Format partition ${params.partition} as ${params.filesystem}${params.label ? ` (${params.label})` : ''}`
    case 'move':
      return `Move partition ${params.partition}`
    case 'set_flag':
      return `${(params.state as boolean) ? 'Set' : 'Unset'} ${params.flag} flag on partition ${params.partition}`
    default:
      return `Unknown operation on ${operation.device}`
  }
}

export function OperationQueue({
  operations,
  onRemove,
  onApplyAll,
  isApplying = false,
}: OperationQueueProps) {
  // Sort by sequence
  const sortedOperations = [...operations].sort((a, b) => a.sequence - b.sequence)

  const pendingCount = operations.filter(op => op.status === 'pending').length
  const runningCount = operations.filter(op => op.status === 'running').length
  const completedCount = operations.filter(op => op.status === 'completed').length
  const failedCount = operations.filter(op => op.status === 'failed').length

  const canApply = pendingCount > 0 && !isApplying
  const isEmpty = operations.length === 0

  if (isEmpty) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-6">
        <div className="text-center text-gray-500">
          <svg
            className="mx-auto h-12 w-12 text-gray-300"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1}
              d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
            />
          </svg>
          <h3 className="mt-2 text-sm font-medium text-gray-900">No pending operations</h3>
          <p className="mt-1 text-sm text-gray-500">
            Use the partition tools to add operations to the queue.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      {/* Header */}
      <div className="bg-gray-50 px-4 py-3 border-b border-gray-200">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h3 className="text-sm font-medium text-gray-900">
              Operation Queue
            </h3>
            <div className="flex items-center gap-2">
              {pendingCount > 0 && (
                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800">
                  {pendingCount} pending
                </span>
              )}
              {runningCount > 0 && (
                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-800">
                  {runningCount} running
                </span>
              )}
              {completedCount > 0 && (
                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">
                  {completedCount} completed
                </span>
              )}
              {failedCount > 0 && (
                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800">
                  {failedCount} failed
                </span>
              )}
            </div>
          </div>
          <Button
            onClick={onApplyAll}
            disabled={!canApply}
            size="sm"
            className="ml-4"
          >
            {isApplying ? (
              <>
                <svg
                  className="animate-spin -ml-1 mr-2 h-4 w-4"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  />
                </svg>
                Applying...
              </>
            ) : (
              <>Apply All ({pendingCount})</>
            )}
          </Button>
        </div>
      </div>

      {/* Warning Banner */}
      {pendingCount > 0 && (
        <div className="bg-amber-50 border-b border-amber-100 px-4 py-2">
          <div className="flex items-center gap-2 text-sm text-amber-800">
            <svg className="h-4 w-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
            <span>
              Operations are queued but not yet applied. Click "Apply All" to execute changes.
            </span>
          </div>
        </div>
      )}

      {/* Operation List */}
      <ul className="divide-y divide-gray-200">
        {sortedOperations.map((operation, index) => {
          const isPending = operation.status === 'pending'
          const isRunning = operation.status === 'running'
          const isFailed = operation.status === 'failed'

          return (
            <li
              key={operation.id}
              className={`px-4 py-3 ${isRunning ? 'bg-yellow-50' : isFailed ? 'bg-red-50' : ''}`}
            >
              <div className="flex items-start gap-3">
                {/* Sequence Number */}
                <div className="flex-shrink-0 w-6 h-6 rounded-full bg-gray-200 flex items-center justify-center text-xs font-medium text-gray-600">
                  {index + 1}
                </div>

                {/* Operation Icon */}
                <div className={`flex-shrink-0 p-1.5 rounded ${
                  operation.operation === 'delete' ? 'bg-red-100 text-red-600' :
                  operation.operation === 'format' ? 'bg-yellow-100 text-yellow-600' :
                  operation.operation === 'create' ? 'bg-green-100 text-green-600' :
                  'bg-blue-100 text-blue-600'
                }`}>
                  {OPERATION_ICONS[operation.operation] || OPERATION_ICONS.resize}
                </div>

                {/* Operation Details */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-gray-900">
                      {PARTITION_OPERATION_TYPE_LABELS[operation.operation]}
                    </span>
                    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${STATUS_COLORS[operation.status]}`}>
                      {PARTITION_OPERATION_STATUS_LABELS[operation.status]}
                    </span>
                  </div>
                  <p className="text-sm text-gray-600 mt-0.5">
                    {getOperationDescription(operation)}
                  </p>
                  <p className="text-xs text-gray-400 mt-0.5">
                    Device: {operation.device}
                  </p>
                  {isFailed && operation.error_message && (
                    <p className="text-sm text-red-600 mt-1 bg-red-50 p-2 rounded">
                      Error: {operation.error_message}
                    </p>
                  )}
                </div>

                {/* Remove Button (only for pending operations) */}
                {isPending && !isApplying && (
                  <button
                    type="button"
                    onClick={() => onRemove(operation.id)}
                    className="flex-shrink-0 p-1 text-gray-400 hover:text-red-600 transition-colors"
                    title="Remove from queue"
                    aria-label="Remove operation from queue"
                  >
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                )}

                {/* Running Spinner */}
                {isRunning && (
                  <div className="flex-shrink-0">
                    <svg
                      className="animate-spin h-5 w-5 text-yellow-600"
                      fill="none"
                      viewBox="0 0 24 24"
                    >
                      <circle
                        className="opacity-25"
                        cx="12"
                        cy="12"
                        r="10"
                        stroke="currentColor"
                        strokeWidth="4"
                      />
                      <path
                        className="opacity-75"
                        fill="currentColor"
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                      />
                    </svg>
                  </div>
                )}

                {/* Completed Check */}
                {operation.status === 'completed' && (
                  <div className="flex-shrink-0">
                    <svg className="h-5 w-5 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                )}
              </div>
            </li>
          )
        })}
      </ul>

      {/* Footer with count summary */}
      <div className="bg-gray-50 px-4 py-2 border-t border-gray-200">
        <p className="text-xs text-gray-500">
          {operations.length} operation{operations.length !== 1 ? 's' : ''} in queue
          {pendingCount > 0 && ` | ${pendingCount} pending`}
        </p>
      </div>
    </div>
  )
}

export default OperationQueue
