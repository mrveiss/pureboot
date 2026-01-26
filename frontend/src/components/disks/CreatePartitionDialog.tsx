/**
 * Dialog for creating new partitions in unallocated space.
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
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui/select'
import type { Disk } from '@/types/partition'
import { FILESYSTEM_TYPES } from '@/types/partition'

interface CreatePartitionDialogProps {
  isOpen: boolean
  onClose: () => void
  disk: Disk
  unallocatedStart: number
  unallocatedEnd: number
  onConfirm: (startBytes: number, endBytes: number, filesystem: string, label?: string) => void
}

// Filesystem descriptions for user guidance
const FILESYSTEM_DESCRIPTIONS: Record<string, string> = {
  ext4: 'Linux default. Best for general-purpose Linux systems.',
  ext3: 'Older Linux filesystem with journaling. Good compatibility.',
  ext2: 'Legacy Linux filesystem without journaling.',
  xfs: 'High-performance filesystem. Good for large files.',
  btrfs: 'Modern copy-on-write filesystem with snapshots.',
  ntfs: 'Windows filesystem. Required for Windows compatibility.',
  fat32: 'Universal compatibility. 4GB file size limit.',
  fat16: 'Legacy FAT filesystem. Small partition support only.',
  swap: 'Linux swap space. Used for virtual memory.',
  'linux-swap': 'Linux swap space. Used for virtual memory.',
}

// Filesystem colors
const FILESYSTEM_COLORS: Record<string, string> = {
  ext4: 'bg-green-100 text-green-800',
  ext3: 'bg-green-100 text-green-700',
  ext2: 'bg-green-100 text-green-600',
  xfs: 'bg-blue-100 text-blue-800',
  btrfs: 'bg-purple-100 text-purple-800',
  ntfs: 'bg-cyan-100 text-cyan-800',
  fat32: 'bg-yellow-100 text-yellow-800',
  fat16: 'bg-yellow-100 text-yellow-700',
  swap: 'bg-gray-100 text-gray-800',
  'linux-swap': 'bg-gray-100 text-gray-800',
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

// Minimum partition size (1 MiB for alignment)
const MIN_PARTITION_SIZE = 1024 * 1024

export function CreatePartitionDialog({
  isOpen,
  onClose,
  disk,
  unallocatedStart,
  unallocatedEnd,
  onConfirm,
}: CreatePartitionDialogProps) {
  const availableSpace = unallocatedEnd - unallocatedStart
  const maxSizeBytes = availableSpace

  const [sizeGiB, setSizeGiB] = React.useState(bytesToGiB(availableSpace))
  const [sizeBytes, setSizeBytes] = React.useState(availableSpace)
  const [filesystem, setFilesystem] = React.useState<string>('ext4')
  const [label, setLabel] = React.useState('')
  const [useFullSpace, setUseFullSpace] = React.useState(true)
  const [sliderValue, setSliderValue] = React.useState(100)

  // Reset state when dialog opens
  React.useEffect(() => {
    if (isOpen) {
      setSizeBytes(availableSpace)
      setSizeGiB(bytesToGiB(availableSpace))
      setFilesystem('ext4')
      setLabel('')
      setUseFullSpace(true)
      setSliderValue(100)
    }
  }, [isOpen, availableSpace])

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
    const newSize = Math.round(MIN_PARTITION_SIZE + ((maxSizeBytes - MIN_PARTITION_SIZE) * percent / 100))
    setSizeBytes(newSize)
    setSizeGiB(bytesToGiB(newSize))
    setUseFullSpace(percent === 100)
  }

  const handleGiBInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    const gib = parseFloat(value) || 0
    setSizeGiB(gib)
    const bytes = giBToBytes(gib)
    setSizeBytes(bytes)
    setUseFullSpace(bytes >= maxSizeBytes)
    // Update slider
    const range = maxSizeBytes - MIN_PARTITION_SIZE
    const offset = bytes - MIN_PARTITION_SIZE
    setSliderValue(range > 0 ? Math.max(0, Math.min(100, (offset / range) * 100)) : 100)
  }

  const handleUseFullSpaceChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const checked = e.target.checked
    setUseFullSpace(checked)
    if (checked) {
      setSizeBytes(maxSizeBytes)
      setSizeGiB(bytesToGiB(maxSizeBytes))
      setSliderValue(100)
    }
  }

  const isValidSize = sizeBytes >= MIN_PARTITION_SIZE && sizeBytes <= maxSizeBytes
  const canCreate = isValidSize && filesystem

  // Calculate actual start and end (aligned to 1 MiB boundaries)
  const alignedStart = Math.ceil(unallocatedStart / (1024 * 1024)) * (1024 * 1024)
  const actualEndBytes = useFullSpace ? unallocatedEnd : alignedStart + sizeBytes

  const handleConfirm = () => {
    if (canCreate) {
      onConfirm(alignedStart, actualEndBytes, filesystem, label || undefined)
      onClose()
    }
  }

  const selectedDescription = FILESYSTEM_DESCRIPTIONS[filesystem] || 'No description available.'

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Create New Partition</DialogTitle>
          <DialogDescription>
            Create a new partition on {disk.device}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Available Space Info */}
          <div className="bg-gray-50 p-3 rounded-lg">
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div>
                <span className="text-gray-500">Disk:</span>
                <span className="ml-2 font-medium">{disk.device}</span>
              </div>
              <div>
                <span className="text-gray-500">Total Disk Size:</span>
                <span className="ml-2 font-medium">{formatSize(disk.size_bytes)}</span>
              </div>
              <div>
                <span className="text-gray-500">Available Space:</span>
                <span className="ml-2 font-medium text-green-600">{formatSize(availableSpace)}</span>
              </div>
              <div>
                <span className="text-gray-500">Partition Table:</span>
                <span className="ml-2 font-medium">{disk.partition_table || 'Unknown'}</span>
              </div>
            </div>
          </div>

          {/* Filesystem Selection */}
          <div className="space-y-2">
            <label className="block text-sm font-medium text-gray-700">
              Filesystem Type
            </label>
            <Select value={filesystem} onValueChange={setFilesystem}>
              <SelectTrigger>
                <SelectValue placeholder="Select filesystem" />
              </SelectTrigger>
              <SelectContent>
                {FILESYSTEM_TYPES.map((fs) => (
                  <SelectItem key={fs} value={fs}>
                    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium mr-2 ${FILESYSTEM_COLORS[fs] || 'bg-gray-100 text-gray-800'}`}>
                      {fs}
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-gray-500">{selectedDescription}</p>
          </div>

          {/* Use Full Space Checkbox */}
          <div className="flex items-center gap-2">
            <input
              id="use-full-space"
              type="checkbox"
              checked={useFullSpace}
              onChange={handleUseFullSpaceChange}
              className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <label htmlFor="use-full-space" className="text-sm text-gray-700">
              Use all available space ({formatSize(availableSpace)})
            </label>
          </div>

          {/* Size Controls (only shown when not using full space) */}
          {!useFullSpace && (
            <div className="space-y-4 pl-6 border-l-2 border-gray-200">
              {/* Size Slider */}
              <div className="space-y-3">
                <label className="block text-sm font-medium text-gray-700">
                  Partition Size
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
                  <span>{formatSize(MIN_PARTITION_SIZE)}</span>
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
                    min={bytesToGiB(MIN_PARTITION_SIZE)}
                    max={bytesToGiB(maxSizeBytes)}
                    value={sizeGiB.toFixed(2)}
                    onChange={handleGiBInputChange}
                    className={!isValidSize ? 'border-red-500 focus:ring-red-500' : ''}
                  />
                </div>
                <div className="flex-1 pt-6">
                  <span className="text-sm text-gray-600">
                    = {formatSize(sizeBytes)}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Label Input */}
          <div className="space-y-2">
            <label htmlFor="label-input" className="block text-sm font-medium text-gray-700">
              Volume Label (Optional)
            </label>
            <Input
              id="label-input"
              type="text"
              placeholder="e.g., Data, Backup, System"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              maxLength={16}
            />
            <p className="text-xs text-gray-500">
              A name to identify this partition. Max 16 characters.
            </p>
          </div>

          {/* Preview */}
          <div className="bg-blue-50 p-3 rounded-lg space-y-2">
            <h4 className="text-sm font-medium text-blue-800">Summary</h4>
            <div className="grid grid-cols-2 gap-2 text-sm text-blue-700">
              <div>
                <span className="text-blue-600">Filesystem:</span>
                <span className="ml-2 font-medium">{filesystem}</span>
              </div>
              <div>
                <span className="text-blue-600">Size:</span>
                <span className="ml-2 font-medium">{formatSize(useFullSpace ? maxSizeBytes : sizeBytes)}</span>
              </div>
              {label && (
                <div className="col-span-2">
                  <span className="text-blue-600">Label:</span>
                  <span className="ml-2 font-medium">{label}</span>
                </div>
              )}
            </div>

            {/* Visual representation */}
            <div className="mt-3">
              <div className="h-4 bg-gray-200 rounded-full overflow-hidden relative">
                <div
                  className="h-full bg-blue-500 transition-all duration-150"
                  style={{ width: `${((useFullSpace ? maxSizeBytes : sizeBytes) / disk.size_bytes) * 100}%` }}
                />
              </div>
              <p className="text-xs text-blue-600 mt-1">
                New partition will use {((useFullSpace ? maxSizeBytes : sizeBytes) / disk.size_bytes * 100).toFixed(1)}% of disk
              </p>
            </div>
          </div>

          {/* Validation Error */}
          {!isValidSize && !useFullSpace && (
            <p className="text-sm text-red-600">
              Size must be between {formatSize(MIN_PARTITION_SIZE)} and {formatSize(maxSizeBytes)}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={!canCreate}
          >
            Create Partition
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default CreatePartitionDialog
