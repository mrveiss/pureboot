/**
 * Partition management page for a node.
 * Provides visual disk editor with partition operations queue.
 */
import { useState, useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  ArrowLeft,
  HardDrive,
  RefreshCw,
  Plus,
  AlertCircle,
  Loader2,
} from 'lucide-react'
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
} from '@/components/ui'
import {
  DiskVisualizer,
  PartitionTable,
  ResizeDialog,
  FormatDialog,
  CreatePartitionDialog,
  OperationQueue,
} from '@/components/disks'
import {
  useNode,
  useNodeDisks,
  useTriggerDiskScan,
  usePartitionOperations,
  useQueueOperation,
  useRemoveOperation,
  useApplyOperations,
} from '@/hooks'
import { usePartitionUpdates } from '@/hooks/usePartitionUpdates'
import type { Partition, Disk, PartitionOperationRequest } from '@/types/partition'

/**
 * Find unallocated space regions on a disk.
 */
interface UnallocatedRegion {
  start: number
  end: number
  size: number
}

function findUnallocatedRegions(disk: Disk): UnallocatedRegion[] {
  const regions: UnallocatedRegion[] = []
  const sortedPartitions = [...disk.partitions].sort((a, b) => a.start_bytes - b.start_bytes)

  let currentPos = 0

  for (const partition of sortedPartitions) {
    if (partition.start_bytes > currentPos) {
      regions.push({
        start: currentPos,
        end: partition.start_bytes,
        size: partition.start_bytes - currentPos,
      })
    }
    currentPos = partition.end_bytes
  }

  // Check for trailing space
  if (currentPos < disk.size_bytes) {
    regions.push({
      start: currentPos,
      end: disk.size_bytes,
      size: disk.size_bytes - currentPos,
    })
  }

  return regions
}

/**
 * Format bytes to human-readable string.
 */
function formatSize(bytes: number): string {
  if (bytes >= 1024 ** 4) return `${(bytes / 1024 ** 4).toFixed(1)} TB`
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${bytes} B`
}

export function PartitionTool() {
  const { nodeId } = useParams<{ nodeId: string }>()

  // Fetch node details for display
  const { data: nodeResponse } = useNode(nodeId ?? '')
  const node = nodeResponse?.data

  // Fetch disks for this node
  const { data: disksResponse, isLoading, error, refetch } = useNodeDisks(nodeId)
  const disks = disksResponse?.data ?? []

  // Trigger disk scan mutation
  const triggerScan = useTriggerDiskScan()

  // Enable real-time partition updates
  const { isConnected } = usePartitionUpdates(nodeId)

  // Selected disk state
  const [selectedDiskDevice, setSelectedDiskDevice] = useState<string | null>(null)

  // Dialog states
  const [selectedPartition, setSelectedPartition] = useState<Partition | null>(null)
  const [resizeDialogOpen, setResizeDialogOpen] = useState(false)
  const [formatDialogOpen, setFormatDialogOpen] = useState(false)
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [createRegion, setCreateRegion] = useState<UnallocatedRegion | null>(null)

  // Get the selected disk
  const selectedDisk = useMemo(() => {
    if (!selectedDiskDevice) {
      // Auto-select first disk if none selected
      return disks.length > 0 ? disks[0] : null
    }
    return disks.find(d => d.device === selectedDiskDevice) ?? null
  }, [disks, selectedDiskDevice])

  // Fetch operations for selected disk
  const { data: operationsResponse } = usePartitionOperations(
    nodeId,
    selectedDisk?.device
  )
  const operations = operationsResponse?.data ?? []

  // Mutations for partition operations
  const queueOperation = useQueueOperation()
  const removeOperation = useRemoveOperation()
  const applyOperations = useApplyOperations()

  // Find unallocated regions
  const unallocatedRegions = useMemo(() => {
    if (!selectedDisk) return []
    return findUnallocatedRegions(selectedDisk)
  }, [selectedDisk])

  // Has unallocated space?
  const hasUnallocatedSpace = unallocatedRegions.some(r => r.size > 1024 * 1024) // > 1MB

  // Handle disk scan
  const handleScanDisks = () => {
    if (!nodeId) return
    triggerScan.mutate(nodeId, {
      onSuccess: () => {
        // Refetch will happen via WebSocket updates
        refetch()
      },
    })
  }

  // Handle resize operation
  const handleResize = (partition: Partition) => {
    setSelectedPartition(partition)
    setResizeDialogOpen(true)
  }

  const handleResizeConfirm = (newSizeBytes: number) => {
    if (!nodeId || !selectedDisk || !selectedPartition) return

    const operation: PartitionOperationRequest = {
      operation: 'resize',
      params: {
        partition: selectedPartition.number,
        new_size_bytes: newSizeBytes,
      },
    }

    queueOperation.mutate({
      nodeId,
      device: selectedDisk.device,
      operation,
    })
  }

  // Handle format operation
  const handleFormat = (partition: Partition) => {
    setSelectedPartition(partition)
    setFormatDialogOpen(true)
  }

  const handleFormatConfirm = (filesystem: string, label?: string) => {
    if (!nodeId || !selectedDisk || !selectedPartition) return

    const operation: PartitionOperationRequest = {
      operation: 'format',
      params: {
        partition: selectedPartition.number,
        filesystem,
        label,
      },
    }

    queueOperation.mutate({
      nodeId,
      device: selectedDisk.device,
      operation,
    })
  }

  // Handle delete operation
  const handleDelete = (partition: Partition) => {
    setSelectedPartition(partition)
    setDeleteDialogOpen(true)
  }

  const handleDeleteConfirm = () => {
    if (!nodeId || !selectedDisk || !selectedPartition) return

    const operation: PartitionOperationRequest = {
      operation: 'delete',
      params: {
        partition: selectedPartition.number,
      },
    }

    queueOperation.mutate(
      {
        nodeId,
        device: selectedDisk.device,
        operation,
      },
      {
        onSuccess: () => setDeleteDialogOpen(false),
      }
    )
  }

  // Handle create partition
  const handleCreate = () => {
    if (unallocatedRegions.length === 0) return
    // Use the largest unallocated region
    const largest = unallocatedRegions.reduce((a, b) => (a.size > b.size ? a : b))
    setCreateRegion(largest)
    setCreateDialogOpen(true)
  }

  const handleCreateConfirm = (
    startBytes: number,
    endBytes: number,
    filesystem: string,
    label?: string
  ) => {
    if (!nodeId || !selectedDisk) return

    const operation: PartitionOperationRequest = {
      operation: 'create',
      params: {
        start_bytes: startBytes,
        end_bytes: endBytes,
        filesystem,
        label,
      },
    }

    queueOperation.mutate({
      nodeId,
      device: selectedDisk.device,
      operation,
    })
  }

  // Handle remove operation from queue
  const handleRemoveOperation = (operationId: string) => {
    if (!nodeId || !selectedDisk) return

    removeOperation.mutate({
      nodeId,
      device: selectedDisk.device,
      operationId,
    })
  }

  // Handle apply all operations
  const handleApplyAll = () => {
    if (!nodeId || !selectedDisk) return

    applyOperations.mutate({
      nodeId,
      device: selectedDisk.device,
    })
  }

  // Handle partition selection
  const handlePartitionSelect = (partition: Partition) => {
    setSelectedPartition(prev =>
      prev?.number === partition.number ? null : partition
    )
  }

  // Loading state
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          <span>Loading disk information...</span>
        </div>
      </div>
    )
  }

  // Error state
  if (error) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" asChild>
          <Link to={`/nodes/${nodeId}`}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Node
          </Link>
        </Button>
        <Card>
          <CardContent className="pt-6">
            <div className="text-center text-destructive">
              <AlertCircle className="h-12 w-12 mx-auto mb-4" />
              <p>{error instanceof Error ? error.message : 'Failed to load disk information'}</p>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" asChild>
            <Link to={`/nodes/${nodeId}`}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back
            </Link>
          </Button>
          <div>
            <h2 className="text-2xl font-bold flex items-center gap-2">
              <HardDrive className="h-6 w-6" />
              Partition Manager
            </h2>
            <p className="text-muted-foreground">
              {node?.hostname || node?.mac_address || nodeId}
            </p>
          </div>
          {isConnected && (
            <div className="flex items-center gap-1 text-xs text-green-600">
              <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
              Live
            </div>
          )}
        </div>
        <Button
          variant="outline"
          onClick={handleScanDisks}
          disabled={triggerScan.isPending}
        >
          {triggerScan.isPending ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="mr-2 h-4 w-4" />
          )}
          Scan Disks
        </Button>
      </div>

      {/* No disks found */}
      {disks.length === 0 && (
        <Card>
          <CardContent className="pt-6">
            <div className="text-center">
              <HardDrive className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
              <h3 className="text-lg font-medium">No Disks Found</h3>
              <p className="text-muted-foreground mt-2">
                No disk information is available for this node. Click "Scan Disks" to
                request a disk scan from the node agent.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Main content */}
      {disks.length > 0 && (
        <div className="grid gap-6 lg:grid-cols-3">
          {/* Left column - Disk visualization and table */}
          <div className="lg:col-span-2 space-y-6">
            {/* Disk Selector */}
            {disks.length > 1 && (
              <Card>
                <CardContent className="pt-6">
                  <div className="flex items-center gap-4">
                    <label className="text-sm font-medium">Select Disk:</label>
                    <Select
                      value={selectedDisk?.device ?? ''}
                      onValueChange={setSelectedDiskDevice}
                    >
                      <SelectTrigger className="w-64">
                        <SelectValue placeholder="Select a disk" />
                      </SelectTrigger>
                      <SelectContent>
                        {disks.map((disk) => (
                          <SelectItem key={disk.id} value={disk.device}>
                            <div className="flex items-center gap-2">
                              <HardDrive className="h-4 w-4" />
                              <span>{disk.device}</span>
                              <span className="text-muted-foreground">
                                ({formatSize(disk.size_bytes)})
                              </span>
                            </div>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Disk Visualizer */}
            {selectedDisk && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center justify-between">
                    <span className="flex items-center gap-2">
                      <HardDrive className="h-5 w-5" />
                      {selectedDisk.device}
                    </span>
                    <div className="flex items-center gap-2 text-sm font-normal text-muted-foreground">
                      {selectedDisk.model && <span>{selectedDisk.model}</span>}
                      <span>{formatSize(selectedDisk.size_bytes)}</span>
                      {selectedDisk.partition_table && (
                        <span className="uppercase text-xs bg-muted px-2 py-0.5 rounded">
                          {selectedDisk.partition_table}
                        </span>
                      )}
                    </div>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <DiskVisualizer
                    disk={selectedDisk}
                    selectedPartition={selectedPartition?.number}
                    onPartitionClick={handlePartitionSelect}
                    height={64}
                  />

                  {/* Create partition button */}
                  {hasUnallocatedSpace && (
                    <div className="flex justify-end">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleCreate}
                        disabled={queueOperation.isPending}
                      >
                        <Plus className="mr-2 h-4 w-4" />
                        Create Partition
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            {/* Partition Table */}
            {selectedDisk && (
              <Card>
                <CardHeader>
                  <CardTitle>Partitions</CardTitle>
                </CardHeader>
                <CardContent>
                  <PartitionTable
                    partitions={selectedDisk.partitions}
                    device={selectedDisk.device}
                    selectedPartition={selectedPartition?.number}
                    onPartitionSelect={handlePartitionSelect}
                    onResizeClick={handleResize}
                    onFormatClick={handleFormat}
                    onDeleteClick={handleDelete}
                    pendingOperations={operations}
                    disabled={queueOperation.isPending || applyOperations.isPending}
                  />
                </CardContent>
              </Card>
            )}
          </div>

          {/* Right column - Operation Queue */}
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Operation Queue</CardTitle>
              </CardHeader>
              <CardContent>
                <OperationQueue
                  operations={operations}
                  onRemove={handleRemoveOperation}
                  onApplyAll={handleApplyAll}
                  isApplying={applyOperations.isPending}
                />
              </CardContent>
            </Card>

            {/* Disk Info Card */}
            {selectedDisk && (
              <Card>
                <CardHeader>
                  <CardTitle>Disk Information</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Device</span>
                    <span className="font-mono">{selectedDisk.device}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Size</span>
                    <span>{formatSize(selectedDisk.size_bytes)}</span>
                  </div>
                  {selectedDisk.model && (
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Model</span>
                      <span>{selectedDisk.model}</span>
                    </div>
                  )}
                  {selectedDisk.serial && (
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Serial</span>
                      <span className="font-mono text-xs">{selectedDisk.serial}</span>
                    </div>
                  )}
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Partition Table</span>
                    <span className="uppercase">{selectedDisk.partition_table || 'Unknown'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Partitions</span>
                    <span>{selectedDisk.partitions.length}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Last Scanned</span>
                    <span>{new Date(selectedDisk.scanned_at).toLocaleString()}</span>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      )}

      {/* Resize Dialog */}
      {selectedPartition && selectedDisk && (
        <ResizeDialog
          isOpen={resizeDialogOpen}
          onClose={() => {
            setResizeDialogOpen(false)
            setSelectedPartition(null)
          }}
          partition={selectedPartition}
          disk={selectedDisk}
          onConfirm={handleResizeConfirm}
        />
      )}

      {/* Format Dialog */}
      {selectedPartition && (
        <FormatDialog
          isOpen={formatDialogOpen}
          onClose={() => {
            setFormatDialogOpen(false)
            setSelectedPartition(null)
          }}
          partition={selectedPartition}
          onConfirm={handleFormatConfirm}
        />
      )}

      {/* Create Partition Dialog */}
      {selectedDisk && createRegion && (
        <CreatePartitionDialog
          isOpen={createDialogOpen}
          onClose={() => {
            setCreateDialogOpen(false)
            setCreateRegion(null)
          }}
          disk={selectedDisk}
          unallocatedStart={createRegion.start}
          unallocatedEnd={createRegion.end}
          onConfirm={handleCreateConfirm}
        />
      )}

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Delete Partition</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete this partition?
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            {selectedPartition && selectedDisk && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                <div className="flex items-start gap-3">
                  <AlertCircle className="h-5 w-5 text-red-600 mt-0.5 flex-shrink-0" />
                  <div>
                    <h4 className="text-sm font-medium text-red-800">
                      Warning: All Data Will Be Lost
                    </h4>
                    <p className="text-sm text-red-700 mt-1">
                      Deleting partition {selectedDisk.device}{selectedPartition.number} will
                      permanently erase all data ({formatSize(selectedPartition.size_bytes)}).
                      This action cannot be undone.
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteDialogOpen(false)}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteConfirm}
              disabled={queueOperation.isPending}
            >
              {queueOperation.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Deleting...
                </>
              ) : (
                'Delete Partition'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export default PartitionTool
