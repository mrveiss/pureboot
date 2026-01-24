/**
 * Dialog for resizing partitions with size constraints and preview.
 */
import * as React from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { Partition, Disk } from '@/types/partition'

interface ResizeDialogProps {
  isOpen: boolean
  onClose: () => void
  partition: Partition
  disk: Disk
  onConfirm: (newSizeBytes: number) => void
}

function formatSize(bytes: number): string {
  if (bytes >= 1024 ** 4) return `${(bytes / 1024 ** 4).toFixed(2)} TB`
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(2)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(2)} KB`
  return `${bytes} B`
}

function bytesToGiB(bytes: number): number {
  return bytes / (1024 ** 3)
}

function giBToBytes(gib: number): number {
  return Math.round(gib * (1024 ** 3))
}

export function ResizeDialog({
  isOpen,
  onClose,
  partition,
  disk,
  onConfirm,
}: ResizeDialogProps) {
  // Calculate constraints
  const minSizeBytes = partition.min_size_bytes ?? partition.used_bytes ?? 1024 * 1024 // 1MB minimum

  // Max size: partition size + available space after partition
  const partitionEndBytes = partition.end_bytes
  const diskSizeBytes = disk.size_bytes

  // Find next partition to determine max available space
  const sortedPartitions = [...disk.partitions].sort((a, b) => a.start_bytes - b.start_bytes)
  const partitionIndex = sortedPartitions.findIndex(p => p.number === partition.number)
  const nextPartition = sortedPartitions[partitionIndex + 1]
  const maxEndBytes = nextPartition ? nextPartition.start_bytes : diskSizeBytes
  const maxSizeBytes = maxEndBytes - partition.start_bytes

  const [newSizeGiB, setNewSizeGiB] = React.useState(bytesToGiB(partition.size_bytes))
  const [newSizeBytes, setNewSizeBytes] = React.useState(partition.size_bytes)
  const [sliderValue, setSliderValue] = React.useState(50) // Percentage between min and max

  // Reset state when dialog opens
  React.useEffect(() => {
    if (isOpen) {
      setNewSizeBytes(partition.size_bytes)
      setNewSizeGiB(bytesToGiB(partition.size_bytes))
      // Calculate initial slider position
      const range = maxSizeBytes - minSizeBytes
      const currentOffset = partition.size_bytes - minSizeBytes
      setSliderValue(range > 0 ? (currentOffset / range) * 100 : 50)
    }
  }, [isOpen, partition.size_bytes, minSizeBytes, maxSizeBytes])

  // Handle keyboard escape
  React.useEffect(() => {
    if (!isOpen) return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  const handleSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const percent = Number(e.target.value)
    setSliderValue(percent)
    const range = maxSizeBytes - minSizeBytes
    const newSize = Math.round(minSizeBytes + (range * percent / 100))
    setNewSizeBytes(newSize)
    setNewSizeGiB(bytesToGiB(newSize))
  }

  const handleGiBInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    const gib = parseFloat(value) || 0
    setNewSizeGiB(gib)
    const bytes = giBToBytes(gib)
    setNewSizeBytes(bytes)
    // Update slider
    const range = maxSizeBytes - minSizeBytes
    const offset = bytes - minSizeBytes
    setSliderValue(range > 0 ? Math.max(0, Math.min(100, (offset / range) * 100)) : 50)
  }

  const isValidSize = newSizeBytes >= minSizeBytes && newSizeBytes <= maxSizeBytes
  const sizeChanged = newSizeBytes !== partition.size_bytes
  const sizeDelta = newSizeBytes - partition.size_bytes

  const handleConfirm = () => {
    if (isValidSize && sizeChanged) {
      onConfirm(newSizeBytes)
      onClose()
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Resize Partition</DialogTitle>
          <DialogDescription>
            Adjust the size of {disk.device}{partition.number}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Current Size Info */}
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-gray-500">Current Size:</span>
              <span className="ml-2 font-medium">{formatSize(partition.size_bytes)}</span>
            </div>
            <div>
              <span className="text-gray-500">Used:</span>
              <span className="ml-2 font-medium">
                {partition.used_bytes !== null ? formatSize(partition.used_bytes) : 'Unknown'}
              </span>
            </div>
          </div>

          {/* Size Constraints */}
          <div className="grid grid-cols-2 gap-4 text-sm bg-gray-50 p-3 rounded-lg">
            <div>
              <span className="text-gray-500">Minimum:</span>
              <span className="ml-2 font-medium">{formatSize(minSizeBytes)}</span>
            </div>
            <div>
              <span className="text-gray-500">Maximum:</span>
              <span className="ml-2 font-medium">{formatSize(maxSizeBytes)}</span>
            </div>
          </div>

          {/* Size Slider */}
          <div className="space-y-3">
            <label className="block text-sm font-medium text-gray-700">
              New Size
            </label>
            <input
              type="range"
              min={0}
              max={100}
              step={0.1}
              value={sliderValue}
              onChange={handleSliderChange}
              className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
            />
            <div className="flex justify-between text-xs text-gray-500">
              <span>{formatSize(minSizeBytes)}</span>
              <span>{formatSize(maxSizeBytes)}</span>
            </div>
          </div>

          {/* Size Input */}
          <div className="flex items-center gap-3">
            <div className="flex-1">
              <label htmlFor="size-input" className="block text-sm font-medium text-gray-700 mb-1">
                Size (GiB)
              </label>
              <Input
                id="size-input"
                type="number"
                step={0.01}
                min={bytesToGiB(minSizeBytes)}
                max={bytesToGiB(maxSizeBytes)}
                value={newSizeGiB.toFixed(2)}
                onChange={handleGiBInputChange}
                className={!isValidSize ? 'border-red-500 focus:ring-red-500' : ''}
              />
            </div>
            <div className="flex-1 pt-6">
              <span className="text-sm text-gray-600">
                = {formatSize(newSizeBytes)}
              </span>
            </div>
          </div>

          {/* Preview */}
          <div className="bg-gray-50 p-3 rounded-lg space-y-2">
            <h4 className="text-sm font-medium text-gray-700">Preview</h4>
            <div className="flex items-center gap-2 text-sm">
              <span className="text-gray-600">{formatSize(partition.size_bytes)}</span>
              <span className="text-gray-400">-&gt;</span>
              <span className={`font-medium ${sizeDelta > 0 ? 'text-green-600' : sizeDelta < 0 ? 'text-red-600' : 'text-gray-600'}`}>
                {formatSize(newSizeBytes)}
              </span>
              {sizeDelta !== 0 && (
                <span className={`text-xs ${sizeDelta > 0 ? 'text-green-600' : 'text-red-600'}`}>
                  ({sizeDelta > 0 ? '+' : ''}{formatSize(Math.abs(sizeDelta))})
                </span>
              )}
            </div>

            {/* Visual bar */}
            <div className="h-4 bg-gray-200 rounded-full overflow-hidden relative">
              <div
                className="h-full bg-blue-500 transition-all duration-150"
                style={{ width: `${(newSizeBytes / maxSizeBytes) * 100}%` }}
              />
              {partition.used_bytes !== null && (
                <div
                  className="absolute top-0 left-0 h-full bg-blue-700"
                  style={{ width: `${(partition.used_bytes / maxSizeBytes) * 100}%` }}
                />
              )}
            </div>
            <div className="flex justify-between text-xs text-gray-500">
              <span>{partition.used_bytes !== null ? 'Used' : ''}</span>
              <span>Free space</span>
            </div>
          </div>

          {/* Validation Error */}
          {!isValidSize && (
            <p className="text-sm text-red-600">
              Size must be between {formatSize(minSizeBytes)} and {formatSize(maxSizeBytes)}
            </p>
          )}

          {/* Warning for shrinking */}
          {sizeDelta < 0 && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3">
              <p className="text-sm text-yellow-800">
                <strong>Warning:</strong> Shrinking a partition may cause data loss if the filesystem cannot be reduced safely. Ensure you have a backup.
              </p>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={!isValidSize || !sizeChanged}
          >
            Resize
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default ResizeDialog
