import { useState } from 'react'
import {
  Folder,
  File,
  ChevronRight,
  Home,
  Upload,
  FolderPlus,
  Download,
  Trash2,
} from 'lucide-react'
import {
  Button,
  Input,
  Checkbox,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  Label,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui'
import { useStorageFiles, useCreateFolder, useDeleteFiles, useStorageBackends } from '@/hooks'
import { storageFilesApi } from '@/api'
import type { StorageFile } from '@/types'
import { cn } from '@/lib/utils'

function formatBytes(bytes: number | null): string {
  if (bytes === null || bytes === 0) return '—'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString()
}

interface FileBrowserProps {
  initialBackendId?: string
}

export function FileBrowser({ initialBackendId }: FileBrowserProps) {
  const [backendId, setBackendId] = useState(initialBackendId ?? '')
  const [currentPath, setCurrentPath] = useState('/')
  const [selectedFiles, setSelectedFiles] = useState<Set<string>>(new Set())
  const [isNewFolderOpen, setIsNewFolderOpen] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')

  const { data: backendsResponse } = useStorageBackends()
  const { data: filesResponse, isLoading } = useStorageFiles(backendId, currentPath)
  const createFolder = useCreateFolder()
  const deleteFiles = useDeleteFiles()

  const backends = backendsResponse?.data ?? []
  const files = filesResponse?.data ?? []

  const pathParts = currentPath.split('/').filter(Boolean)

  const toggleFile = (path: string) => {
    const newSet = new Set(selectedFiles)
    if (newSet.has(path)) {
      newSet.delete(path)
    } else {
      newSet.add(path)
    }
    setSelectedFiles(newSet)
  }

  const selectAll = () => {
    if (selectedFiles.size === files.length) {
      setSelectedFiles(new Set())
    } else {
      setSelectedFiles(new Set(files.map((f) => f.path)))
    }
  }

  const navigateTo = (path: string) => {
    setCurrentPath(path)
    setSelectedFiles(new Set())
  }

  const navigateToIndex = (index: number) => {
    const newPath = '/' + pathParts.slice(0, index + 1).join('/')
    navigateTo(newPath)
  }

  const handleFileClick = (file: StorageFile) => {
    if (file.type === 'directory') {
      navigateTo(file.path)
    }
  }

  const handleCreateFolder = () => {
    if (newFolderName.trim() && backendId) {
      createFolder.mutate(
        { backendId, path: currentPath, name: newFolderName.trim() },
        {
          onSuccess: () => {
            setIsNewFolderOpen(false)
            setNewFolderName('')
          },
        }
      )
    }
  }

  const handleDelete = () => {
    if (selectedFiles.size > 0 && backendId) {
      if (confirm(`Delete ${selectedFiles.size} item(s)?`)) {
        deleteFiles.mutate(
          { backendId, paths: Array.from(selectedFiles) },
          {
            onSuccess: () => setSelectedFiles(new Set()),
          }
        )
      }
    }
  }

  const handleDownload = () => {
    if (selectedFiles.size === 1 && backendId) {
      const path = Array.from(selectedFiles)[0]
      const url = storageFilesApi.getDownloadUrl(backendId, path)
      window.open(url, '_blank')
    }
  }

  const someSelected = selectedFiles.size > 0
  const allSelected = files.length > 0 && selectedFiles.size === files.length
  const singleFileSelected = selectedFiles.size === 1 && files.find((f) => f.path === Array.from(selectedFiles)[0])?.type === 'file'

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-4">
        <div className="w-64">
          <Select value={backendId} onValueChange={(v) => { setBackendId(v); setCurrentPath('/'); setSelectedFiles(new Set()) }}>
            <SelectTrigger>
              <SelectValue placeholder="Select backend..." />
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

        <div className="flex-1" />

        <Button variant="outline" size="sm" onClick={() => setIsNewFolderOpen(true)} disabled={!backendId}>
          <FolderPlus className="h-4 w-4 mr-2" />
          New Folder
        </Button>

        <Button variant="outline" size="sm" disabled={!backendId}>
          <Upload className="h-4 w-4 mr-2" />
          Upload
        </Button>

        {someSelected && (
          <>
            <Button variant="outline" size="sm" onClick={handleDownload} disabled={!singleFileSelected}>
              <Download className="h-4 w-4 mr-2" />
              Download
            </Button>
            <Button variant="outline" size="sm" onClick={handleDelete} className="text-destructive">
              <Trash2 className="h-4 w-4 mr-2" />
              Delete ({selectedFiles.size})
            </Button>
          </>
        )}
      </div>

      {/* Breadcrumb */}
      {backendId && (
        <div className="flex items-center gap-1 text-sm">
          <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => navigateTo('/')}>
            <Home className="h-4 w-4" />
          </Button>
          {pathParts.map((part, index) => (
            <div key={index} className="flex items-center">
              <ChevronRight className="h-4 w-4 text-muted-foreground" />
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2"
                onClick={() => navigateToIndex(index)}
              >
                {part}
              </Button>
            </div>
          ))}
        </div>
      )}

      {/* File List */}
      <div className="rounded-md border">
        {/* Header */}
        <div className="flex items-center border-b bg-muted/50 text-sm font-medium">
          <div className="w-12 p-3 flex items-center justify-center">
            <Checkbox
              checked={allSelected}
              indeterminate={someSelected && !allSelected}
              onCheckedChange={selectAll}
              disabled={!backendId || files.length === 0}
            />
          </div>
          <div className="flex-1 p-3">Name</div>
          <div className="w-24 p-3 text-right">Size</div>
          <div className="w-32 p-3">Type</div>
          <div className="w-32 p-3">Modified</div>
        </div>

        {/* Body */}
        <div className="max-h-[400px] overflow-auto">
          {!backendId ? (
            <div className="p-8 text-center text-muted-foreground">
              Select a storage backend to browse files
            </div>
          ) : isLoading ? (
            <div className="p-8 text-center text-muted-foreground">Loading...</div>
          ) : files.length === 0 ? (
            <div className="p-8 text-center text-muted-foreground">
              This folder is empty
            </div>
          ) : (
            files.map((file) => (
              <div
                key={file.path}
                className={cn(
                  'flex items-center border-b last:border-0 hover:bg-muted/30',
                  selectedFiles.has(file.path) && 'bg-muted/50'
                )}
              >
                <div className="w-12 p-3 flex items-center justify-center" onClick={(e) => e.stopPropagation()}>
                  <Checkbox
                    checked={selectedFiles.has(file.path)}
                    onCheckedChange={() => toggleFile(file.path)}
                  />
                </div>
                <div
                  className="flex-1 p-3 flex items-center gap-2 cursor-pointer"
                  onClick={() => handleFileClick(file)}
                >
                  {file.type === 'directory' ? (
                    <Folder className="h-4 w-4 text-blue-500" />
                  ) : (
                    <File className="h-4 w-4 text-muted-foreground" />
                  )}
                  <span className="truncate">{file.name}</span>
                  {file.type === 'directory' && file.item_count !== undefined && (
                    <span className="text-xs text-muted-foreground">({file.item_count} items)</span>
                  )}
                </div>
                <div className="w-24 p-3 text-right text-sm text-muted-foreground">
                  {formatBytes(file.size)}
                </div>
                <div className="w-32 p-3 text-sm text-muted-foreground">
                  {file.type === 'directory' ? 'Folder' : file.mime_type ?? 'File'}
                </div>
                <div className="w-32 p-3 text-sm text-muted-foreground">
                  {formatDate(file.modified_at)}
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* New Folder Dialog */}
      <Dialog open={isNewFolderOpen} onOpenChange={setIsNewFolderOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New Folder</DialogTitle>
          </DialogHeader>
          <div className="py-4">
            <Label htmlFor="folder-name">Folder Name</Label>
            <Input
              id="folder-name"
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              placeholder="New folder"
              className="mt-2"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsNewFolderOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreateFolder} disabled={!newFolderName.trim() || createFolder.isPending}>
              {createFolder.isPending ? 'Creating...' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
