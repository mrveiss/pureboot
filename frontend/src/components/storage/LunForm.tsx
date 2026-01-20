import { useState, useEffect } from 'react'
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
  Checkbox,
} from '@/components/ui'
import { useStorageBackends } from '@/hooks'
import { LUN_PURPOSE_LABELS, type IscsiLun, type LunPurpose } from '@/types'

interface LunFormProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  lun?: IscsiLun | null
  onSubmit: (data: Partial<IscsiLun>) => void
  isPending: boolean
}

export function LunForm({ open, onOpenChange, lun, onSubmit, isPending }: LunFormProps) {
  const [name, setName] = useState('')
  const [sizeGb, setSizeGb] = useState(100)
  const [targetId, setTargetId] = useState('')
  const [purpose, setPurpose] = useState<LunPurpose>('boot_from_san')
  const [chapEnabled, setChapEnabled] = useState(false)

  const { data: backendsResponse } = useStorageBackends()
  const backends = backendsResponse?.data ?? []
  const iscsiBackends = backends.filter((b) => b.type === 'iscsi')

  const isEditing = !!lun

  useEffect(() => {
    if (lun) {
      setName(lun.name)
      setSizeGb(lun.size_gb)
      setTargetId(lun.target_id)
      setPurpose(lun.purpose)
      setChapEnabled(lun.chap_enabled)
    } else {
      setName('')
      setSizeGb(100)
      setTargetId(iscsiBackends[0]?.id ?? '')
      setPurpose('boot_from_san')
      setChapEnabled(false)
    }
  }, [lun, open, iscsiBackends])

  const handleSubmit = () => {
    onSubmit({
      name,
      size_gb: sizeGb,
      target_id: targetId,
      purpose,
      chap_enabled: chapEnabled,
    })
  }

  const isValid = name.trim() !== '' && targetId !== '' && sizeGb > 0

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEditing ? 'Edit iSCSI LUN' : 'Create iSCSI LUN'}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="lun-name">Name</Label>
            <Input
              id="lun-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., web-server-01-boot"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="lun-size">Size (GB)</Label>
            <Input
              id="lun-size"
              type="number"
              value={sizeGb}
              onChange={(e) => setSizeGb(parseInt(e.target.value) || 0)}
              min={1}
              disabled={isEditing}
            />
            {isEditing && (
              <p className="text-xs text-muted-foreground">Size cannot be changed after creation</p>
            )}
          </div>

          <div className="space-y-2">
            <Label>iSCSI Target</Label>
            <Select value={targetId} onValueChange={setTargetId} disabled={isEditing}>
              <SelectTrigger>
                <SelectValue placeholder="Select target..." />
              </SelectTrigger>
              <SelectContent>
                {iscsiBackends.map((b) => (
                  <SelectItem key={b.id} value={b.id}>
                    {b.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {iscsiBackends.length === 0 && (
              <p className="text-xs text-destructive">No iSCSI backends configured</p>
            )}
          </div>

          <div className="space-y-2">
            <Label>Purpose</Label>
            <Select value={purpose} onValueChange={(v) => setPurpose(v as LunPurpose)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(LUN_PURPOSE_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              {purpose === 'boot_from_san' && 'Node boots and runs from this LUN'}
              {purpose === 'install_source' && 'Mounted during installation only'}
              {purpose === 'auto_provision' && 'Assigned automatically to new nodes'}
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Checkbox
              id="lun-chap"
              checked={chapEnabled}
              onCheckedChange={(checked) => setChapEnabled(!!checked)}
            />
            <Label htmlFor="lun-chap" className="font-normal">
              Enable CHAP authentication
            </Label>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={!isValid || isPending}>
            {isPending ? 'Saving...' : isEditing ? 'Save' : 'Create'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
