import { useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  Button,
  Input,
  Label,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui'
import { useCreateSite } from '@/hooks'
import type { SiteCreate, AutonomyLevel, CachePolicy, ConflictResolution } from '@/types/site'

interface CreateSiteDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

const INITIAL_FORM: SiteCreate = {
  name: '',
  description: null,
  autonomy_level: 'readonly',
  cache_policy: 'minimal',
  conflict_resolution: 'central_wins',
}

export function CreateSiteDialog({ open, onOpenChange }: CreateSiteDialogProps) {
  const [form, setForm] = useState<SiteCreate>({ ...INITIAL_FORM })
  const createSite = useCreateSite()

  const handleCreate = () => {
    createSite.mutate(form, {
      onSuccess: () => {
        onOpenChange(false)
        setForm({ ...INITIAL_FORM })
      },
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create Site</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="site-name">Name</Label>
            <Input
              id="site-name"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="e.g., datacenter-west"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="site-description">Description</Label>
            <Input
              id="site-description"
              value={form.description ?? ''}
              onChange={(e) =>
                setForm({ ...form, description: e.target.value || null })
              }
              placeholder="Optional description"
            />
          </div>
          <div className="space-y-2">
            <Label>Autonomy Level</Label>
            <Select
              value={form.autonomy_level ?? 'readonly'}
              onValueChange={(v) => setForm({ ...form, autonomy_level: v as AutonomyLevel })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="readonly">Read Only</SelectItem>
                <SelectItem value="limited">Limited</SelectItem>
                <SelectItem value="full">Full</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Cache Policy</Label>
            <Select
              value={form.cache_policy ?? 'minimal'}
              onValueChange={(v) => setForm({ ...form, cache_policy: v as CachePolicy })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="minimal">Minimal</SelectItem>
                <SelectItem value="assigned">Assigned</SelectItem>
                <SelectItem value="mirror">Mirror</SelectItem>
                <SelectItem value="pattern">Pattern</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Conflict Resolution</Label>
            <Select
              value={form.conflict_resolution ?? 'central_wins'}
              onValueChange={(v) =>
                setForm({ ...form, conflict_resolution: v as ConflictResolution })
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="central_wins">Central Wins</SelectItem>
                <SelectItem value="last_write">Last Write Wins</SelectItem>
                <SelectItem value="site_wins">Site Wins</SelectItem>
                <SelectItem value="manual">Manual</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleCreate}
            disabled={!form.name || createSite.isPending}
          >
            {createSite.isPending ? 'Creating...' : 'Create Site'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
