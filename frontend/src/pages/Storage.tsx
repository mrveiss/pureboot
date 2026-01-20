import { useState } from 'react'
import { Plus, HardDrive, FolderOpen, Database, RefreshCw } from 'lucide-react'
import { Tabs, TabsList, TabsTrigger, TabsContent, Button, Card, CardContent } from '@/components/ui'
import {
  BackendCard,
  BackendForm,
  FileBrowser,
  LunTable,
  LunForm,
  SyncJobCard,
  SyncJobForm,
} from '@/components/storage'
import {
  useStorageBackends,
  useCreateStorageBackend,
  useUpdateStorageBackend,
  useDeleteStorageBackend,
  useTestStorageBackend,
  useCreateLun,
  useUpdateLun,
  useSyncJobs,
  useCreateSyncJob,
  useUpdateSyncJob,
  useDeleteSyncJob,
  useRunSyncJob,
} from '@/hooks'
import type { StorageBackend, IscsiLun, SyncJob } from '@/types'

export function Storage() {
  const [activeTab, setActiveTab] = useState('backends')

  // Backends state
  const [isBackendFormOpen, setIsBackendFormOpen] = useState(false)
  const [editingBackend, setEditingBackend] = useState<StorageBackend | null>(null)

  // LUNs state
  const [isLunFormOpen, setIsLunFormOpen] = useState(false)
  const [editingLun, setEditingLun] = useState<IscsiLun | null>(null)

  // Sync Jobs state
  const [isSyncJobFormOpen, setIsSyncJobFormOpen] = useState(false)
  const [editingSyncJob, setEditingSyncJob] = useState<SyncJob | null>(null)

  // Queries
  const { data: backendsResponse, isLoading: backendsLoading } = useStorageBackends()
  const { data: syncJobsResponse, isLoading: syncJobsLoading } = useSyncJobs()

  // Mutations
  const createBackend = useCreateStorageBackend()
  const updateBackend = useUpdateStorageBackend()
  const deleteBackend = useDeleteStorageBackend()
  const testBackend = useTestStorageBackend()
  const createLun = useCreateLun()
  const updateLun = useUpdateLun()
  const createSyncJob = useCreateSyncJob()
  const updateSyncJob = useUpdateSyncJob()
  const deleteSyncJob = useDeleteSyncJob()
  const runSyncJob = useRunSyncJob()

  const backends = backendsResponse?.data ?? []
  const syncJobs = syncJobsResponse?.data ?? []

  // Backend handlers
  const handleBackendSubmit = (data: Partial<StorageBackend>) => {
    if (editingBackend) {
      updateBackend.mutate(
        { backendId: editingBackend.id, data },
        {
          onSuccess: () => {
            setIsBackendFormOpen(false)
            setEditingBackend(null)
          },
        }
      )
    } else {
      createBackend.mutate(data, {
        onSuccess: () => setIsBackendFormOpen(false),
      })
    }
  }

  const handleBackendDelete = (backend: StorageBackend) => {
    if (confirm(`Delete storage backend "${backend.name}"?`)) {
      deleteBackend.mutate(backend.id)
    }
  }

  const handleBackendTest = async (backend: StorageBackend) => {
    const result = await testBackend.mutateAsync(backend.id)
    alert(result.data?.message ?? 'Test completed')
  }

  // LUN handlers
  const handleLunSubmit = (data: Partial<IscsiLun>) => {
    if (editingLun) {
      updateLun.mutate(
        { lunId: editingLun.id, data },
        {
          onSuccess: () => {
            setIsLunFormOpen(false)
            setEditingLun(null)
          },
        }
      )
    } else {
      createLun.mutate(data, {
        onSuccess: () => setIsLunFormOpen(false),
      })
    }
  }

  // Sync Job handlers
  const handleSyncJobSubmit = (data: Partial<SyncJob>) => {
    if (editingSyncJob) {
      updateSyncJob.mutate(
        { jobId: editingSyncJob.id, data },
        {
          onSuccess: () => {
            setIsSyncJobFormOpen(false)
            setEditingSyncJob(null)
          },
        }
      )
    } else {
      createSyncJob.mutate(data, {
        onSuccess: () => setIsSyncJobFormOpen(false),
      })
    }
  }

  const handleSyncJobDelete = (job: SyncJob) => {
    if (confirm(`Delete sync job "${job.name}"?`)) {
      deleteSyncJob.mutate(job.id)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-3xl font-bold tracking-tight">Storage</h2>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="backends" className="gap-2">
            <HardDrive className="h-4 w-4" />
            Backends
          </TabsTrigger>
          <TabsTrigger value="files" className="gap-2">
            <FolderOpen className="h-4 w-4" />
            Files
          </TabsTrigger>
          <TabsTrigger value="luns" className="gap-2">
            <Database className="h-4 w-4" />
            iSCSI LUNs
          </TabsTrigger>
          <TabsTrigger value="sync" className="gap-2">
            <RefreshCw className="h-4 w-4" />
            Sync Jobs
          </TabsTrigger>
        </TabsList>

        {/* Backends Tab */}
        <TabsContent value="backends">
          <div className="space-y-4">
            <div className="flex justify-end">
              <Button onClick={() => { setEditingBackend(null); setIsBackendFormOpen(true) }}>
                <Plus className="h-4 w-4 mr-2" />
                Add Backend
              </Button>
            </div>

            {backendsLoading ? (
              <div className="text-muted-foreground">Loading backends...</div>
            ) : backends.length === 0 ? (
              <Card>
                <CardContent className="pt-6">
                  <div className="text-center text-muted-foreground">
                    <HardDrive className="mx-auto h-12 w-12 mb-4 opacity-50" />
                    <p>No storage backends configured.</p>
                    <p className="text-sm mt-1">Add a backend to start managing storage.</p>
                  </div>
                </CardContent>
              </Card>
            ) : (
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {backends.map((backend) => (
                  <BackendCard
                    key={backend.id}
                    backend={backend}
                    onEdit={(b) => { setEditingBackend(b); setIsBackendFormOpen(true) }}
                    onDelete={handleBackendDelete}
                    onTest={handleBackendTest}
                  />
                ))}
              </div>
            )}
          </div>
        </TabsContent>

        {/* Files Tab */}
        <TabsContent value="files">
          <FileBrowser />
        </TabsContent>

        {/* iSCSI LUNs Tab */}
        <TabsContent value="luns">
          <LunTable
            onEdit={(lun) => { setEditingLun(lun); setIsLunFormOpen(true) }}
            onCreate={() => { setEditingLun(null); setIsLunFormOpen(true) }}
          />
        </TabsContent>

        {/* Sync Jobs Tab */}
        <TabsContent value="sync">
          <div className="space-y-4">
            <div className="flex justify-end">
              <Button onClick={() => { setEditingSyncJob(null); setIsSyncJobFormOpen(true) }}>
                <Plus className="h-4 w-4 mr-2" />
                Create Job
              </Button>
            </div>

            {syncJobsLoading ? (
              <div className="text-muted-foreground">Loading sync jobs...</div>
            ) : syncJobs.length === 0 ? (
              <Card>
                <CardContent className="pt-6">
                  <div className="text-center text-muted-foreground">
                    <RefreshCw className="mx-auto h-12 w-12 mb-4 opacity-50" />
                    <p>No sync jobs configured.</p>
                    <p className="text-sm mt-1">Create a job to sync files from external sources.</p>
                  </div>
                </CardContent>
              </Card>
            ) : (
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {syncJobs.map((job) => (
                  <SyncJobCard
                    key={job.id}
                    job={job}
                    onEdit={(j) => { setEditingSyncJob(j); setIsSyncJobFormOpen(true) }}
                    onDelete={handleSyncJobDelete}
                    onRun={(j) => runSyncJob.mutate(j.id)}
                    isRunning={runSyncJob.isPending}
                  />
                ))}
              </div>
            )}
          </div>
        </TabsContent>
      </Tabs>

      {/* Dialogs */}
      <BackendForm
        open={isBackendFormOpen}
        onOpenChange={setIsBackendFormOpen}
        backend={editingBackend}
        onSubmit={handleBackendSubmit}
        isPending={createBackend.isPending || updateBackend.isPending}
      />

      <LunForm
        open={isLunFormOpen}
        onOpenChange={setIsLunFormOpen}
        lun={editingLun}
        onSubmit={handleLunSubmit}
        isPending={createLun.isPending || updateLun.isPending}
      />

      <SyncJobForm
        open={isSyncJobFormOpen}
        onOpenChange={setIsSyncJobFormOpen}
        job={editingSyncJob}
        onSubmit={handleSyncJobSubmit}
        isPending={createSyncJob.isPending || updateSyncJob.isPending}
      />
    </div>
  )
}
