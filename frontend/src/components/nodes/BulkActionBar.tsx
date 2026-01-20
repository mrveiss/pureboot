import { useState } from 'react'
import {
  GitBranch,
  FolderOpen,
  Tag,
  RefreshCw,
  Archive,
  Trash2,
  X,
} from 'lucide-react'
import { Button, Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, Input, Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui'
import { useSelectionStore } from '@/stores'
import { useGroups, useBulkAssignGroup, useBulkAddTag, useBulkChangeState } from '@/hooks'
import { NODE_STATE_LABELS, type NodeState } from '@/types'
import { cn } from '@/lib/utils'

type ActionDialogType = 'group' | 'tag' | 'state' | null

export function BulkActionBar() {
  const { selectedNodeIds, deselectAll } = useSelectionStore()
  const [activeDialog, setActiveDialog] = useState<ActionDialogType>(null)
  const [selectedGroup, setSelectedGroup] = useState<string>('')
  const [tagInput, setTagInput] = useState('')
  const [selectedState, setSelectedState] = useState<NodeState | ''>('')

  const { data: groupsResponse } = useGroups()
  const assignGroup = useBulkAssignGroup()
  const addTag = useBulkAddTag()
  const changeState = useBulkChangeState()

  const selectedCount = selectedNodeIds.size

  if (selectedCount === 0) return null

  const groups = groupsResponse?.data ?? []
  const nodeIds = Array.from(selectedNodeIds)

  const handleAssignGroup = () => {
    if (selectedGroup) {
      assignGroup.mutate({
        nodeIds,
        groupId: selectedGroup === 'none' ? null : selectedGroup,
      })
    }
    setActiveDialog(null)
    setSelectedGroup('')
  }

  const handleAddTag = () => {
    if (tagInput.trim()) {
      addTag.mutate({ nodeIds, tag: tagInput.trim() })
    }
    setActiveDialog(null)
    setTagInput('')
  }

  const handleChangeState = () => {
    if (selectedState) {
      changeState.mutate({ nodeIds, newState: selectedState })
    }
    setActiveDialog(null)
    setSelectedState('')
  }

  const allowedStates: NodeState[] = ['pending', 'retired', 'reprovision']

  return (
    <>
      <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40">
        <div className="flex items-center gap-2 bg-background border rounded-lg shadow-lg px-4 py-3">
          <span className="text-sm font-medium mr-2">
            {selectedCount} node{selectedCount !== 1 ? 's' : ''} selected
          </span>

          <div className="h-6 w-px bg-border" />

          <Button
            variant="ghost"
            size="sm"
            onClick={() => setActiveDialog('group')}
            className="gap-2"
          >
            <FolderOpen className="h-4 w-4" />
            Assign Group
          </Button>

          <Button
            variant="ghost"
            size="sm"
            onClick={() => setActiveDialog('tag')}
            className="gap-2"
          >
            <Tag className="h-4 w-4" />
            Add Tag
          </Button>

          <Button
            variant="ghost"
            size="sm"
            onClick={() => setActiveDialog('state')}
            className="gap-2"
          >
            <RefreshCw className="h-4 w-4" />
            Change State
          </Button>

          <div className="h-6 w-px bg-border" />

          <Button variant="ghost" size="sm" onClick={deselectAll}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Assign Group Dialog */}
      <Dialog open={activeDialog === 'group'} onOpenChange={(open) => !open && setActiveDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Assign Group to {selectedCount} Nodes</DialogTitle>
          </DialogHeader>
          <div className="py-4">
            <Select value={selectedGroup} onValueChange={setSelectedGroup}>
              <SelectTrigger>
                <SelectValue placeholder="Select a group..." />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">No Group</SelectItem>
                {groups.map((group) => (
                  <SelectItem key={group.id} value={group.id}>
                    {group.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setActiveDialog(null)}>
              Cancel
            </Button>
            <Button onClick={handleAssignGroup} disabled={!selectedGroup || assignGroup.isPending}>
              {assignGroup.isPending ? 'Assigning...' : 'Assign'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Add Tag Dialog */}
      <Dialog open={activeDialog === 'tag'} onOpenChange={(open) => !open && setActiveDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Tag to {selectedCount} Nodes</DialogTitle>
          </DialogHeader>
          <div className="py-4">
            <Input
              placeholder="Enter tag name..."
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setActiveDialog(null)}>
              Cancel
            </Button>
            <Button onClick={handleAddTag} disabled={!tagInput.trim() || addTag.isPending}>
              {addTag.isPending ? 'Adding...' : 'Add Tag'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Change State Dialog */}
      <Dialog open={activeDialog === 'state'} onOpenChange={(open) => !open && setActiveDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Change State of {selectedCount} Nodes</DialogTitle>
          </DialogHeader>
          <div className="py-4">
            <p className="text-sm text-muted-foreground mb-4">
              Note: State changes are only applied to nodes where the transition is valid.
            </p>
            <Select value={selectedState} onValueChange={(v) => setSelectedState(v as NodeState)}>
              <SelectTrigger>
                <SelectValue placeholder="Select new state..." />
              </SelectTrigger>
              <SelectContent>
                {allowedStates.map((state) => (
                  <SelectItem key={state} value={state}>
                    {NODE_STATE_LABELS[state]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setActiveDialog(null)}>
              Cancel
            </Button>
            <Button onClick={handleChangeState} disabled={!selectedState || changeState.isPending}>
              {changeState.isPending ? 'Changing...' : 'Change State'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
