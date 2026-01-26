/**
 * Visual editor for clone resize plans.
 * Allows users to view and edit partition sizes when cloning to a smaller target disk.
 */
import { useState, useMemo } from 'react'
import {
  HardDrive,
  ArrowRight,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Save,
  RotateCcw,
} from 'lucide-react'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Button,
  Badge,
  Input,
  Label,
} from '@/components/ui'
import { cn } from '@/lib/utils'

// ============== Types ==============

export interface PartitionPlanItem {
  partition: number
  current_size_bytes: number
  new_size_bytes: number
  filesystem: string | null
  action: 'keep' | 'shrink' | 'grow' | 'delete'
  min_size_bytes: number | null
  can_resize: boolean
}

export interface ResizePlan {
  source_disk_bytes: number
  target_disk_bytes: number
  resize_mode: 'none' | 'shrink_source' | 'grow_target'
  partitions: PartitionPlanItem[]
  feasible: boolean
  error_message: string | null
}

interface ResizePlanEditorProps {
  plan: ResizePlan
  onSave: (updatedPlan: ResizePlan) => void
  onCancel?: () => void
  isLoading?: boolean
}

// ============== Utility Functions ==============

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const k = 1024
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(2)} ${units[i]}`
}

function parseBytes(value: string): number {
  const trimmed = value.trim().toUpperCase()
  const match = trimmed.match(/^([\d.]+)\s*(B|KB|MB|GB|TB)?$/)
  if (!match) return 0

  const num = parseFloat(match[1])
  const unit = match[2] || 'B'

  const multipliers: Record<string, number> = {
    B: 1,
    KB: 1024,
    MB: 1024 ** 2,
    GB: 1024 ** 3,
    TB: 1024 ** 4,
  }

  return Math.floor(num * (multipliers[unit] || 1))
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
}

function getFilesystemColor(filesystem: string | null): string {
  if (!filesystem) return FILESYSTEM_COLORS.unknown
  const lower = filesystem.toLowerCase()
  return FILESYSTEM_COLORS[lower] || FILESYSTEM_COLORS.unknown
}

// ============== Sub-Components ==============

interface DiskSizeBarProps {
  label: string
  totalBytes: number
  partitions: PartitionPlanItem[]
  useNewSizes?: boolean
  maxBytes: number
}

function DiskSizeBar({
  label,
  totalBytes,
  partitions,
  useNewSizes = false,
  maxBytes,
}: DiskSizeBarProps) {
  const widthPercent = (totalBytes / maxBytes) * 100

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium">{label}</span>
        <span className="text-muted-foreground">{formatBytes(totalBytes)}</span>
      </div>
      <div
        className="h-8 bg-muted rounded overflow-hidden flex border"
        style={{ width: `${widthPercent}%`, minWidth: '100px' }}
      >
        {partitions.map((p) => {
          const size = useNewSizes ? p.new_size_bytes : p.current_size_bytes
          const partWidthPercent = (size / totalBytes) * 100
          if (partWidthPercent < 0.5) return null

          return (
            <div
              key={p.partition}
              className={cn(
                'h-full flex items-center justify-center text-white text-xs',
                'border-r border-white/20 last:border-r-0',
                getFilesystemColor(p.filesystem)
              )}
              style={{ width: `${partWidthPercent}%`, minWidth: '2px' }}
              title={`Partition ${p.partition}: ${formatBytes(size)}`}
            >
              {partWidthPercent > 10 && <span>{p.partition}</span>}
            </div>
          )
        })}
      </div>
    </div>
  )
}

interface PartitionRowProps {
  partition: PartitionPlanItem
  onChange: (newSizeBytes: number) => void
  disabled?: boolean
}

function PartitionRow({ partition, onChange, disabled }: PartitionRowProps) {
  const [inputValue, setInputValue] = useState(formatBytes(partition.new_size_bytes))

  const handleBlur = () => {
    const parsed = parseBytes(inputValue)
    if (parsed > 0) {
      onChange(parsed)
    } else {
      setInputValue(formatBytes(partition.new_size_bytes))
    }
  }

  const sizeDiff = partition.new_size_bytes - partition.current_size_bytes
  const percentChange = ((sizeDiff / partition.current_size_bytes) * 100).toFixed(1)

  const canEdit = partition.can_resize && partition.action !== 'delete' && !disabled

  return (
    <div className="flex items-center gap-4 p-3 bg-muted/50 rounded-lg">
      {/* Partition info */}
      <div className="flex items-center gap-2 w-24">
        <div className={cn('w-3 h-3 rounded', getFilesystemColor(partition.filesystem))} />
        <span className="font-medium">Part {partition.partition}</span>
      </div>

      {/* Filesystem type */}
      <div className="w-20 text-sm text-muted-foreground">
        {partition.filesystem || 'unknown'}
      </div>

      {/* Current size */}
      <div className="w-24 text-sm">
        <div className="text-muted-foreground text-xs">Current</div>
        <div>{formatBytes(partition.current_size_bytes)}</div>
      </div>

      {/* Arrow */}
      <ArrowRight className="h-4 w-4 text-muted-foreground" />

      {/* New size input */}
      <div className="w-32">
        <div className="text-muted-foreground text-xs">New Size</div>
        {canEdit ? (
          <Input
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onBlur={handleBlur}
            className="h-8 text-sm"
          />
        ) : (
          <div className="text-sm py-1">{formatBytes(partition.new_size_bytes)}</div>
        )}
      </div>

      {/* Min size info */}
      {partition.min_size_bytes !== null && (
        <div className="w-24 text-xs text-muted-foreground">
          Min: {formatBytes(partition.min_size_bytes)}
        </div>
      )}

      {/* Action badge */}
      <Badge
        variant="outline"
        className={cn(
          'capitalize',
          partition.action === 'shrink' && 'border-orange-500 text-orange-600',
          partition.action === 'grow' && 'border-green-500 text-green-600',
          partition.action === 'keep' && 'border-gray-500 text-gray-600',
          partition.action === 'delete' && 'border-red-500 text-red-600'
        )}
      >
        {partition.action}
      </Badge>

      {/* Size change indicator */}
      {sizeDiff !== 0 && (
        <div
          className={cn(
            'text-xs',
            sizeDiff < 0 ? 'text-orange-600' : 'text-green-600'
          )}
        >
          {sizeDiff > 0 ? '+' : ''}
          {percentChange}%
        </div>
      )}

      {/* Resize capability */}
      {!partition.can_resize && (
        <span title="Cannot resize this partition">
          <AlertTriangle className="h-4 w-4 text-yellow-500" />
        </span>
      )}
    </div>
  )
}

// ============== Main Component ==============

export function ResizePlanEditor({
  plan: initialPlan,
  onSave,
  onCancel,
  isLoading = false,
}: ResizePlanEditorProps) {
  const [editedPlan, setEditedPlan] = useState<ResizePlan>(initialPlan)

  // Calculate if the edited plan is feasible
  const calculatedPlan = useMemo(() => {
    const totalNewSize = editedPlan.partitions.reduce(
      (sum, p) => sum + p.new_size_bytes,
      0
    )
    const feasible = totalNewSize <= editedPlan.target_disk_bytes

    // Update actions based on size changes
    const updatedPartitions = editedPlan.partitions.map((p) => {
      let action: PartitionPlanItem['action'] = 'keep'
      if (p.new_size_bytes < p.current_size_bytes) action = 'shrink'
      else if (p.new_size_bytes > p.current_size_bytes) action = 'grow'
      return { ...p, action }
    })

    return {
      ...editedPlan,
      partitions: updatedPartitions,
      feasible,
      error_message: feasible
        ? null
        : `Total partition size (${formatBytes(totalNewSize)}) exceeds target disk (${formatBytes(editedPlan.target_disk_bytes)})`,
    }
  }, [editedPlan])

  const handlePartitionChange = (partitionNum: number, newSizeBytes: number) => {
    setEditedPlan((prev) => ({
      ...prev,
      partitions: prev.partitions.map((p) =>
        p.partition === partitionNum ? { ...p, new_size_bytes: newSizeBytes } : p
      ),
    }))
  }

  const handleReset = () => {
    setEditedPlan(initialPlan)
  }

  const handleSave = () => {
    onSave(calculatedPlan)
  }

  const totalCurrentSize = calculatedPlan.partitions.reduce(
    (sum, p) => sum + p.current_size_bytes,
    0
  )
  const totalNewSize = calculatedPlan.partitions.reduce(
    (sum, p) => sum + p.new_size_bytes,
    0
  )
  const maxBytes = Math.max(
    calculatedPlan.source_disk_bytes,
    calculatedPlan.target_disk_bytes
  )

  const sizeDifference = calculatedPlan.source_disk_bytes - calculatedPlan.target_disk_bytes
  const needsShrinking = sizeDifference > 0

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <HardDrive className="h-5 w-5" />
            Resize Plan
          </CardTitle>
          <div className="flex items-center gap-2">
            {calculatedPlan.feasible ? (
              <Badge variant="outline" className="border-green-500 text-green-600 gap-1">
                <CheckCircle className="h-3 w-3" />
                Feasible
              </Badge>
            ) : (
              <Badge variant="outline" className="border-red-500 text-red-600 gap-1">
                <XCircle className="h-3 w-3" />
                Not Feasible
              </Badge>
            )}
            <Badge variant="outline" className="capitalize">
              {calculatedPlan.resize_mode.replace('_', ' ')}
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Disk size comparison */}
        <div className="space-y-4">
          <h4 className="text-sm font-medium flex items-center gap-2">
            Disk Size Comparison
            {needsShrinking && (
              <Badge variant="outline" className="border-orange-500 text-orange-600 text-xs">
                {formatBytes(sizeDifference)} to shrink
              </Badge>
            )}
          </h4>

          <div className="space-y-3">
            <DiskSizeBar
              label="Source Disk"
              totalBytes={calculatedPlan.source_disk_bytes}
              partitions={calculatedPlan.partitions}
              useNewSizes={false}
              maxBytes={maxBytes}
            />
            <DiskSizeBar
              label="Target Disk"
              totalBytes={calculatedPlan.target_disk_bytes}
              partitions={calculatedPlan.partitions}
              useNewSizes={true}
              maxBytes={maxBytes}
            />
          </div>

          {/* Size summary */}
          <div className="flex items-center justify-between text-sm bg-muted/50 rounded-lg p-3">
            <div>
              <div className="text-muted-foreground">Total Current Size</div>
              <div className="font-medium">{formatBytes(totalCurrentSize)}</div>
            </div>
            <ArrowRight className="h-4 w-4 text-muted-foreground" />
            <div>
              <div className="text-muted-foreground">Total New Size</div>
              <div className="font-medium">{formatBytes(totalNewSize)}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Target Disk</div>
              <div className="font-medium">{formatBytes(calculatedPlan.target_disk_bytes)}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Remaining Space</div>
              <div
                className={cn(
                  'font-medium',
                  calculatedPlan.target_disk_bytes - totalNewSize < 0
                    ? 'text-red-600'
                    : 'text-green-600'
                )}
              >
                {formatBytes(calculatedPlan.target_disk_bytes - totalNewSize)}
              </div>
            </div>
          </div>
        </div>

        {/* Partition list */}
        <div className="space-y-3">
          <Label>Partition Sizes</Label>
          {calculatedPlan.partitions.map((partition) => (
            <PartitionRow
              key={partition.partition}
              partition={partition}
              onChange={(newSize) => handlePartitionChange(partition.partition, newSize)}
              disabled={isLoading}
            />
          ))}
        </div>

        {/* Error message */}
        {calculatedPlan.error_message && (
          <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
            <AlertTriangle className="h-4 w-4 mt-0.5 flex-shrink-0" />
            {calculatedPlan.error_message}
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center justify-end gap-3 pt-4 border-t">
          <Button
            variant="outline"
            onClick={handleReset}
            disabled={isLoading}
          >
            <RotateCcw className="mr-2 h-4 w-4" />
            Reset
          </Button>
          {onCancel && (
            <Button variant="ghost" onClick={onCancel} disabled={isLoading}>
              Cancel
            </Button>
          )}
          <Button
            onClick={handleSave}
            disabled={!calculatedPlan.feasible || isLoading}
          >
            <Save className="mr-2 h-4 w-4" />
            {isLoading ? 'Saving...' : 'Save Plan'}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

export default ResizePlanEditor
