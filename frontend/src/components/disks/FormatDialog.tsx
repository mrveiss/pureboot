/**
 * Dialog for formatting partitions with filesystem selection.
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
import type { Partition } from '@/types/partition'
import { FILESYSTEM_TYPES } from '@/types/partition'

interface FormatDialogProps {
  isOpen: boolean
  onClose: () => void
  partition: Partition
  onConfirm: (filesystem: string, label?: string) => void
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

// Filesystem icons/indicators
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

export function FormatDialog({
  isOpen,
  onClose,
  partition,
  onConfirm,
}: FormatDialogProps) {
  const [filesystem, setFilesystem] = React.useState<string>(partition.filesystem || 'ext4')
  const [label, setLabel] = React.useState<string>(partition.label || '')
  const [confirmText, setConfirmText] = React.useState('')

  // Reset state when dialog opens
  React.useEffect(() => {
    if (isOpen) {
      setFilesystem(partition.filesystem || 'ext4')
      setLabel(partition.label || '')
      setConfirmText('')
    }
  }, [isOpen, partition.filesystem, partition.label])

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

  const isConfirmed = confirmText === 'FORMAT'
  const hasData = partition.used_bytes !== null && partition.used_bytes > 0

  const handleConfirm = () => {
    if (isConfirmed) {
      onConfirm(filesystem, label || undefined)
      onClose()
    }
  }

  const selectedDescription = FILESYSTEM_DESCRIPTIONS[filesystem] || 'No description available.'

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Format Partition</DialogTitle>
          <DialogDescription>
            Create a new filesystem on this partition
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Partition Info */}
          <div className="bg-gray-50 p-3 rounded-lg">
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div>
                <span className="text-gray-500">Partition:</span>
                <span className="ml-2 font-medium">{partition.number}</span>
              </div>
              <div>
                <span className="text-gray-500">Size:</span>
                <span className="ml-2 font-medium">{formatSize(partition.size_bytes)}</span>
              </div>
              <div>
                <span className="text-gray-500">Current FS:</span>
                <span className="ml-2 font-medium">{partition.filesystem || 'None'}</span>
              </div>
              <div>
                <span className="text-gray-500">Current Label:</span>
                <span className="ml-2 font-medium">{partition.label || 'None'}</span>
              </div>
            </div>
          </div>

          {/* Data Loss Warning */}
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <div className="flex items-start gap-3">
              <svg
                className="h-5 w-5 text-red-600 mt-0.5 flex-shrink-0"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                />
              </svg>
              <div>
                <h4 className="text-sm font-medium text-red-800">
                  Warning: All Data Will Be Lost
                </h4>
                <p className="text-sm text-red-700 mt-1">
                  Formatting will permanently erase all data on this partition.
                  {hasData && (
                    <span className="font-medium">
                      {' '}This partition currently contains {formatSize(partition.used_bytes!)} of data.
                    </span>
                  )}
                </p>
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

          {/* Confirmation Input */}
          <div className="space-y-2">
            <label htmlFor="confirm-input" className="block text-sm font-medium text-gray-700">
              Type FORMAT to confirm
            </label>
            <Input
              id="confirm-input"
              type="text"
              placeholder="FORMAT"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value.toUpperCase())}
              className={confirmText && !isConfirmed ? 'border-red-500' : ''}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleConfirm}
            disabled={!isConfirmed}
          >
            Format Partition
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default FormatDialog
