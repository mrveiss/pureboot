import { useState } from 'react'
import { Plus, Pencil, Trash2, Link, Unlink } from 'lucide-react'
import {
  Button,
  Badge,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui'
import { useLuns, useDeleteLun, useAssignLun, useUnassignLun, useNodes } from '@/hooks'
import { LUN_PURPOSE_LABELS, LUN_STATUS_COLORS, type IscsiLun } from '@/types'
import { cn } from '@/lib/utils'

interface LunTableProps {
  onEdit: (lun: IscsiLun) => void
  onCreate: () => void
}

export function LunTable({ onEdit, onCreate }: LunTableProps) {
  const { data: lunsResponse, isLoading } = useLuns()
  const { data: nodesResponse } = useNodes({ limit: 1000 })
  const deleteLun = useDeleteLun()
  const assignLun = useAssignLun()
  const unassignLun = useUnassignLun()

  const [assignDialogLun, setAssignDialogLun] = useState<IscsiLun | null>(null)
  const [selectedNodeId, setSelectedNodeId] = useState('')
  const [deletingLun, setDeletingLun] = useState<IscsiLun | null>(null)

  const luns = lunsResponse?.data ?? []
  const nodes = nodesResponse?.data ?? []

  const handleAssign = () => {
    if (assignDialogLun && selectedNodeId) {
      assignLun.mutate(
        { lunId: assignDialogLun.id, nodeId: selectedNodeId },
        {
          onSuccess: () => {
            setAssignDialogLun(null)
            setSelectedNodeId('')
          },
        }
      )
    }
  }

  const handleUnassign = (lun: IscsiLun) => {
    if (confirm(`Unassign LUN "${lun.name}" from ${lun.assigned_node_name}?`)) {
      unassignLun.mutate(lun.id)
    }
  }

  const handleDelete = () => {
    if (deletingLun) {
      deleteLun.mutate(deletingLun.id, {
        onSuccess: () => setDeletingLun(null),
      })
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={onCreate}>
          <Plus className="h-4 w-4 mr-2" />
          Create LUN
        </Button>
      </div>

      <div className="rounded-md border">
        {/* Header */}
        <div className="flex items-center border-b bg-muted/50 text-sm font-medium">
          <div className="flex-1 p-3">Name</div>
          <div className="w-24 p-3">Size</div>
          <div className="w-40 p-3">Assigned To</div>
          <div className="w-32 p-3">Purpose</div>
          <div className="w-24 p-3">Status</div>
          <div className="w-32 p-3">Actions</div>
        </div>

        {/* Body */}
        <div className="max-h-[500px] overflow-auto">
          {isLoading ? (
            <div className="p-8 text-center text-muted-foreground">Loading LUNs...</div>
          ) : luns.length === 0 ? (
            <div className="p-8 text-center text-muted-foreground">
              No iSCSI LUNs configured
            </div>
          ) : (
            luns.map((lun) => (
              <div key={lun.id} className="flex items-center border-b last:border-0 hover:bg-muted/30">
                <div className="flex-1 p-3">
                  <div className="font-medium">{lun.name}</div>
                  <div className="text-xs text-muted-foreground font-mono truncate">
                    {lun.iqn}
                  </div>
                </div>
                <div className="w-24 p-3 text-sm">{lun.size_gb} GB</div>
                <div className="w-40 p-3 text-sm">
                  {lun.assigned_node_name ?? (
                    <span className="text-muted-foreground">(unassigned)</span>
                  )}
                </div>
                <div className="w-32 p-3">
                  <Badge variant="outline">{LUN_PURPOSE_LABELS[lun.purpose]}</Badge>
                </div>
                <div className="w-24 p-3">
                  <div className="flex items-center gap-2">
                    <div className={cn('h-2 w-2 rounded-full', LUN_STATUS_COLORS[lun.status])} />
                    <span className="text-sm capitalize">{lun.status}</span>
                  </div>
                </div>
                <div className="w-32 p-3 flex gap-1">
                  {lun.assigned_node_id ? (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8"
                      onClick={() => handleUnassign(lun)}
                      title="Unassign"
                    >
                      <Unlink className="h-4 w-4" />
                    </Button>
                  ) : (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8"
                      onClick={() => setAssignDialogLun(lun)}
                      title="Assign to node"
                    >
                      <Link className="h-4 w-4" />
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8"
                    onClick={() => onEdit(lun)}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-destructive"
                    onClick={() => setDeletingLun(lun)}
                    disabled={!!lun.assigned_node_id}
                    title={lun.assigned_node_id ? 'Unassign before deleting' : 'Delete'}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Assign Dialog */}
      <Dialog open={!!assignDialogLun} onOpenChange={(open) => !open && setAssignDialogLun(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Assign LUN to Node</DialogTitle>
          </DialogHeader>
          <div className="py-4">
            <p className="text-sm text-muted-foreground mb-4">
              Assign <strong>{assignDialogLun?.name}</strong> to a node:
            </p>
            <Select value={selectedNodeId} onValueChange={setSelectedNodeId}>
              <SelectTrigger>
                <SelectValue placeholder="Select a node..." />
              </SelectTrigger>
              <SelectContent>
                {nodes.map((node) => (
                  <SelectItem key={node.id} value={node.id}>
                    {node.hostname ?? node.mac_address}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAssignDialogLun(null)}>
              Cancel
            </Button>
            <Button onClick={handleAssign} disabled={!selectedNodeId || assignLun.isPending}>
              {assignLun.isPending ? 'Assigning...' : 'Assign'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <Dialog open={!!deletingLun} onOpenChange={(open) => !open && setDeletingLun(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete LUN</DialogTitle>
          </DialogHeader>
          <p className="py-4">
            Are you sure you want to delete <strong>{deletingLun?.name}</strong>?
            This action cannot be undone.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeletingLun(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDelete} disabled={deleteLun.isPending}>
              {deleteLun.isPending ? 'Deleting...' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
