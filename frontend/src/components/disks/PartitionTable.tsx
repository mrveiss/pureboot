/**
 * Detailed table view of partitions with filesystem info, usage, and action buttons.
 */
import type { Partition, PartitionOperation } from '@/types/partition'
import { PARTITION_OPERATION_STATUS_LABELS } from '@/types/partition'

interface PartitionTableProps {
  partitions: Partition[]
  device: string
  selectedPartition?: number
  onPartitionSelect?: (partition: Partition) => void
  onResizeClick?: (partition: Partition) => void
  onFormatClick?: (partition: Partition) => void
  onDeleteClick?: (partition: Partition) => void
  pendingOperations?: PartitionOperation[]
  disabled?: boolean
}

function formatSize(bytes: number): string {
  if (bytes >= 1024 ** 4) return `${(bytes / 1024 ** 4).toFixed(2)} TB`
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(2)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(2)} KB`
  return `${bytes} B`
}

// Status badge colors (background + text)
const STATUS_BADGE_COLORS: Record<string, string> = {
  pending: 'bg-gray-100 text-gray-800',
  running: 'bg-yellow-100 text-yellow-800',
  completed: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
}

function UsageBar({ percent }: { percent: number | null }) {
  if (percent === null) return <span className="text-gray-400">-</span>

  const color = percent > 90 ? 'bg-red-500' : percent > 70 ? 'bg-yellow-500' : 'bg-green-500'

  return (
    <div className="flex items-center gap-2">
      <div className="w-24 h-2 bg-gray-200 rounded-full overflow-hidden">
        <div
          className={`h-full ${color}`}
          style={{ width: `${Math.min(percent, 100)}%` }}
        />
      </div>
      <span className="text-xs text-gray-600">{percent.toFixed(0)}%</span>
    </div>
  )
}

export function PartitionTable({
  partitions,
  device,
  selectedPartition,
  onPartitionSelect,
  onResizeClick,
  onFormatClick,
  onDeleteClick,
  pendingOperations = [],
  disabled = false,
}: PartitionTableProps) {
  // Check if a partition has pending operations
  const getPartitionOperations = (partitionNumber: number): PartitionOperation[] => {
    return pendingOperations.filter(op => {
      const params = op.params as Record<string, unknown>
      return params.partition === partitionNumber
    })
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Partition
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Filesystem
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Label
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Size
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Usage
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Flags
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Status
            </th>
            <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
              Actions
            </th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {partitions.map((partition) => {
            const isSelected = selectedPartition === partition.number
            const ops = getPartitionOperations(partition.number)
            const hasPendingOps = ops.length > 0

            return (
              <tr
                key={partition.number}
                className={`
                  ${isSelected ? 'bg-blue-50' : 'hover:bg-gray-50'}
                  ${onPartitionSelect ? 'cursor-pointer' : ''}
                  transition-colors
                `}
                onClick={() => onPartitionSelect?.(partition)}
              >
                <td className="px-4 py-3 whitespace-nowrap">
                  <span className="font-medium text-gray-900">
                    {device}{partition.number}
                  </span>
                </td>
                <td className="px-4 py-3 whitespace-nowrap">
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
                    {partition.filesystem || 'unknown'}
                  </span>
                </td>
                <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500">
                  {partition.label || '-'}
                </td>
                <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-900">
                  {formatSize(partition.size_bytes)}
                </td>
                <td className="px-4 py-3 whitespace-nowrap">
                  <UsageBar percent={partition.used_percent} />
                </td>
                <td className="px-4 py-3 whitespace-nowrap">
                  <div className="flex flex-wrap gap-1">
                    {partition.flags.length > 0 ? (
                      partition.flags.map((flag) => (
                        <span
                          key={flag}
                          className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800"
                        >
                          {flag}
                        </span>
                      ))
                    ) : (
                      <span className="text-gray-400">-</span>
                    )}
                  </div>
                </td>
                <td className="px-4 py-3 whitespace-nowrap">
                  {hasPendingOps ? (
                    <div className="flex flex-col gap-1">
                      {ops.map((op) => (
                        <span
                          key={op.id}
                          className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${STATUS_BADGE_COLORS[op.status] || STATUS_BADGE_COLORS.pending}`}
                        >
                          {op.operation}: {PARTITION_OPERATION_STATUS_LABELS[op.status]}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <span className="text-gray-400">-</span>
                  )}
                </td>
                <td className="px-4 py-3 whitespace-nowrap text-right text-sm">
                  <div className="flex justify-end gap-2">
                    {partition.can_shrink && onResizeClick && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          onResizeClick(partition)
                        }}
                        disabled={disabled || hasPendingOps}
                        className="text-blue-600 hover:text-blue-800 disabled:text-gray-400 disabled:cursor-not-allowed"
                        title="Resize partition"
                      >
                        Resize
                      </button>
                    )}
                    {onFormatClick && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          onFormatClick(partition)
                        }}
                        disabled={disabled || hasPendingOps}
                        className="text-yellow-600 hover:text-yellow-800 disabled:text-gray-400 disabled:cursor-not-allowed"
                        title="Format partition"
                      >
                        Format
                      </button>
                    )}
                    {onDeleteClick && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          onDeleteClick(partition)
                        }}
                        disabled={disabled || hasPendingOps}
                        className="text-red-600 hover:text-red-800 disabled:text-gray-400 disabled:cursor-not-allowed"
                        title="Delete partition"
                      >
                        Delete
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            )
          })}
          {partitions.length === 0 && (
            <tr>
              <td colSpan={8} className="px-4 py-8 text-center text-gray-500">
                No partitions found on this disk
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

export default PartitionTable
