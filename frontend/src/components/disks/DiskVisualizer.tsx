/**
 * Visual representation of a disk with partitions shown as proportional colored blocks.
 * Similar to GParted's graphical disk view.
 */
import { useMemo } from 'react'
import { cn } from '@/lib/utils'
import type { Disk, Partition } from '@/types/partition'

interface DiskVisualizerProps {
  disk: Disk
  selectedPartition?: number
  onPartitionClick?: (partition: Partition) => void
  showLabels?: boolean
  height?: number
}

// Color palette for different filesystem types
const FILESYSTEM_COLORS: Record<string, string> = {
  ext4: 'bg-blue-500',
  ext3: 'bg-blue-400',
  ext2: 'bg-blue-300',
  xfs: 'bg-purple-500',
  btrfs: 'bg-green-500',
  ntfs: 'bg-cyan-500',
  fat32: 'bg-yellow-500',
  fat16: 'bg-yellow-400',
  vfat: 'bg-yellow-500',
  exfat: 'bg-orange-500',
  swap: 'bg-red-500',
  'linux-swap': 'bg-red-500',
  efi: 'bg-pink-500',
  unknown: 'bg-gray-400',
  unallocated: 'bg-gray-200',
}

function getFilesystemColor(filesystem: string | null): string {
  if (!filesystem) return FILESYSTEM_COLORS.unknown
  const lower = filesystem.toLowerCase()
  return FILESYSTEM_COLORS[lower] || FILESYSTEM_COLORS.unknown
}

function formatSize(bytes: number): string {
  if (bytes >= 1024 ** 4) return `${(bytes / 1024 ** 4).toFixed(1)} TB`
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${bytes} B`
}

interface VisualizerBlock {
  type: 'partition' | 'unallocated'
  partition?: Partition
  start: number
  end: number
  widthPercent: number
}

export function DiskVisualizer({
  disk,
  selectedPartition,
  onPartitionClick,
  showLabels = true,
  height = 48,
}: DiskVisualizerProps) {
  // Calculate partition blocks with gaps for unallocated space
  const blocks = useMemo<VisualizerBlock[]>(() => {
    const result: VisualizerBlock[] = []

    const totalSize = disk.size_bytes
    if (totalSize === 0) return result

    const sortedPartitions = [...disk.partitions].sort((a, b) => a.start_bytes - b.start_bytes)

    let currentPos = 0

    for (const partition of sortedPartitions) {
      // Add unallocated space before this partition
      if (partition.start_bytes > currentPos) {
        const gapSize = partition.start_bytes - currentPos
        result.push({
          type: 'unallocated',
          start: currentPos,
          end: partition.start_bytes,
          widthPercent: (gapSize / totalSize) * 100,
        })
      }

      // Add the partition
      result.push({
        type: 'partition',
        partition,
        start: partition.start_bytes,
        end: partition.end_bytes,
        widthPercent: (partition.size_bytes / totalSize) * 100,
      })

      currentPos = partition.end_bytes
    }

    // Add trailing unallocated space
    if (currentPos < totalSize) {
      result.push({
        type: 'unallocated',
        start: currentPos,
        end: totalSize,
        widthPercent: ((totalSize - currentPos) / totalSize) * 100,
      })
    }

    return result
  }, [disk])

  const hasUnallocatedSpace = blocks.some(b => b.type === 'unallocated')

  return (
    <div className="space-y-2">
      {/* Disk info header */}
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium text-gray-900">{disk.device}</span>
        <span className="text-gray-500">{formatSize(disk.size_bytes)}</span>
      </div>

      {/* Visual bar */}
      <div
        className="flex w-full overflow-hidden rounded-lg border border-gray-300"
        style={{ height }}
      >
        {blocks.map((block, index) => {
          if (block.type === 'unallocated') {
            return (
              <div
                key={`unallocated-${index}`}
                className={cn(
                  'flex items-center justify-center bg-gray-200',
                  'border-r border-gray-300 last:border-r-0'
                )}
                style={{
                  width: `${block.widthPercent}%`,
                  minWidth: block.widthPercent > 1 ? '2px' : '1px',
                }}
                title={`Unallocated: ${formatSize(block.end - block.start)}`}
              >
                {block.widthPercent > 5 && (
                  <span className="text-xs text-gray-500 truncate px-1">Free</span>
                )}
              </div>
            )
          }

          const partition = block.partition!
          const isSelected = selectedPartition === partition.number
          const color = getFilesystemColor(partition.filesystem)

          return (
            <div
              key={`partition-${partition.number}`}
              className={cn(
                'flex items-center justify-center',
                'border-r border-gray-300 last:border-r-0',
                'transition-all duration-150',
                color,
                isSelected && 'ring-2 ring-offset-1 ring-blue-600',
                onPartitionClick && 'cursor-pointer hover:brightness-110'
              )}
              style={{
                width: `${block.widthPercent}%`,
                minWidth: '4px',
              }}
              onClick={() => onPartitionClick?.(partition)}
              title={`${disk.device}${partition.number}: ${partition.filesystem || 'unknown'} - ${formatSize(partition.size_bytes)}`}
            >
              {showLabels && block.widthPercent > 8 && (
                <div className="flex flex-col items-center text-white text-xs truncate px-1">
                  <span className="font-medium">{partition.number}</span>
                  {block.widthPercent > 15 && (
                    <span className="text-[10px] opacity-80">
                      {formatSize(partition.size_bytes)}
                    </span>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Legend */}
      {showLabels && (
        <div className="flex flex-wrap gap-3 text-xs">
          {disk.partitions.map((partition) => (
            <div
              key={partition.number}
              className="flex items-center gap-1"
            >
              <div
                className={cn('w-3 h-3 rounded', getFilesystemColor(partition.filesystem))}
              />
              <span className="text-gray-600">
                {partition.number}: {partition.filesystem || 'unknown'}
              </span>
            </div>
          ))}
          {hasUnallocatedSpace && (
            <div className="flex items-center gap-1">
              <div className="w-3 h-3 rounded bg-gray-200 border border-gray-300" />
              <span className="text-gray-600">Unallocated</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default DiskVisualizer
