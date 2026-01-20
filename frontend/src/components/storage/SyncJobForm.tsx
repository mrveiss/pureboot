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
import { SYNC_SCHEDULE_LABELS, type SyncJob, type SyncSchedule } from '@/types'

interface SyncJobFormProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  job?: SyncJob | null
  onSubmit: (data: Partial<SyncJob>) => void
  isPending: boolean
}

const DAYS_OF_WEEK = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

export function SyncJobForm({ open, onOpenChange, job, onSubmit, isPending }: SyncJobFormProps) {
  const [name, setName] = useState('')
  const [sourceUrl, setSourceUrl] = useState('')
  const [destinationBackendId, setDestinationBackendId] = useState('')
  const [destinationPath, setDestinationPath] = useState('/')
  const [includePattern, setIncludePattern] = useState('')
  const [excludePattern, setExcludePattern] = useState('')
  const [schedule, setSchedule] = useState<SyncSchedule>('weekly')
  const [scheduleDay, setScheduleDay] = useState(0)
  const [scheduleTime, setScheduleTime] = useState('02:00')
  const [verifyChecksums, setVerifyChecksums] = useState(true)
  const [deleteRemoved, setDeleteRemoved] = useState(true)
  const [keepVersions, setKeepVersions] = useState(0)

  const { data: backendsResponse } = useStorageBackends()
  const backends = backendsResponse?.data ?? []

  const isEditing = !!job

  useEffect(() => {
    if (job) {
      setName(job.name)
      setSourceUrl(job.source_url)
      setDestinationBackendId(job.destination_backend_id)
      setDestinationPath(job.destination_path)
      setIncludePattern(job.include_pattern ?? '')
      setExcludePattern(job.exclude_pattern ?? '')
      setSchedule(job.schedule)
      setScheduleDay(job.schedule_day ?? 0)
      setScheduleTime(job.schedule_time ?? '02:00')
      setVerifyChecksums(job.verify_checksums)
      setDeleteRemoved(job.delete_removed)
      setKeepVersions(job.keep_versions)
    } else {
      setName('')
      setSourceUrl('')
      setDestinationBackendId(backends[0]?.id ?? '')
      setDestinationPath('/')
      setIncludePattern('')
      setExcludePattern('')
      setSchedule('weekly')
      setScheduleDay(0)
      setScheduleTime('02:00')
      setVerifyChecksums(true)
      setDeleteRemoved(true)
      setKeepVersions(0)
    }
  }, [job, open, backends])

  const handleSubmit = () => {
    onSubmit({
      name,
      source_url: sourceUrl,
      destination_backend_id: destinationBackendId,
      destination_path: destinationPath,
      include_pattern: includePattern || undefined,
      exclude_pattern: excludePattern || undefined,
      schedule,
      schedule_day: schedule === 'weekly' || schedule === 'monthly' ? scheduleDay : undefined,
      schedule_time: schedule !== 'manual' ? scheduleTime : undefined,
      verify_checksums: verifyChecksums,
      delete_removed: deleteRemoved,
      keep_versions: keepVersions,
    })
  }

  const isValid = name.trim() !== '' && sourceUrl.trim() !== '' && destinationBackendId !== ''

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEditing ? 'Edit Sync Job' : 'Create Sync Job'}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="job-name">Name</Label>
            <Input
              id="job-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Ubuntu ISOs"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="job-source">Source URL</Label>
            <Input
              id="job-source"
              value={sourceUrl}
              onChange={(e) => setSourceUrl(e.target.value)}
              placeholder="https://releases.ubuntu.com/24.04/"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Destination Backend</Label>
              <Select value={destinationBackendId} onValueChange={setDestinationBackendId}>
                <SelectTrigger>
                  <SelectValue placeholder="Select..." />
                </SelectTrigger>
                <SelectContent>
                  {backends.map((b) => (
                    <SelectItem key={b.id} value={b.id}>
                      {b.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="job-dest-path">Destination Path</Label>
              <Input
                id="job-dest-path"
                value={destinationPath}
                onChange={(e) => setDestinationPath(e.target.value)}
                placeholder="/isos/ubuntu/"
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="job-include">Include Pattern (optional)</Label>
            <Input
              id="job-include"
              value={includePattern}
              onChange={(e) => setIncludePattern(e.target.value)}
              placeholder="*-live-server-amd64.iso"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="job-exclude">Exclude Pattern (optional)</Label>
            <Input
              id="job-exclude"
              value={excludePattern}
              onChange={(e) => setExcludePattern(e.target.value)}
              placeholder="*.zsync, *.torrent"
            />
          </div>

          <div className="space-y-2">
            <Label>Schedule</Label>
            <Select value={schedule} onValueChange={(v) => setSchedule(v as SyncSchedule)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(SYNC_SCHEDULE_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {schedule === 'weekly' && (
            <div className="space-y-2">
              <Label>Day of Week</Label>
              <Select value={scheduleDay.toString()} onValueChange={(v) => setScheduleDay(parseInt(v))}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DAYS_OF_WEEK.map((day, i) => (
                    <SelectItem key={i} value={i.toString()}>
                      {day}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {schedule === 'monthly' && (
            <div className="space-y-2">
              <Label htmlFor="job-day">Day of Month</Label>
              <Input
                id="job-day"
                type="number"
                min={1}
                max={31}
                value={scheduleDay}
                onChange={(e) => setScheduleDay(parseInt(e.target.value) || 1)}
              />
            </div>
          )}

          {schedule !== 'manual' && (
            <div className="space-y-2">
              <Label htmlFor="job-time">Time</Label>
              <Input
                id="job-time"
                type="time"
                value={scheduleTime}
                onChange={(e) => setScheduleTime(e.target.value)}
              />
            </div>
          )}

          <div className="space-y-2">
            <Label>Options</Label>
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <Checkbox
                  id="job-verify"
                  checked={verifyChecksums}
                  onCheckedChange={(checked) => setVerifyChecksums(!!checked)}
                />
                <Label htmlFor="job-verify" className="font-normal">
                  Verify checksums (SHA256)
                </Label>
              </div>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="job-delete"
                  checked={deleteRemoved}
                  onCheckedChange={(checked) => setDeleteRemoved(!!checked)}
                />
                <Label htmlFor="job-delete" className="font-normal">
                  Delete removed files
                </Label>
              </div>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="job-versions">Keep Previous Versions (0 = disabled)</Label>
            <Input
              id="job-versions"
              type="number"
              min={0}
              max={10}
              value={keepVersions}
              onChange={(e) => setKeepVersions(parseInt(e.target.value) || 0)}
            />
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
