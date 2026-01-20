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
import {
  STORAGE_BACKEND_TYPE_LABELS,
  type StorageBackend,
  type StorageBackendType,
  type NfsConfig,
  type IscsiTargetConfig,
  type S3Config,
  type HttpConfig,
} from '@/types'

interface BackendFormProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  backend?: StorageBackend | null
  onSubmit: (data: Partial<StorageBackend>) => void
  isPending: boolean
}

const DEFAULT_NFS: NfsConfig = {
  server: '',
  export_path: '',
  mount_options: 'vers=4.1',
  auth_method: 'none',
}

const DEFAULT_ISCSI: IscsiTargetConfig = {
  target: '',
  port: 3260,
  chap_enabled: false,
}

const DEFAULT_S3: S3Config = {
  endpoint: '',
  bucket: '',
  region: '',
  access_key_id: '',
  cdn_enabled: false,
}

const DEFAULT_HTTP: HttpConfig = {
  base_url: '',
  auth_method: 'none',
}

export function BackendForm({ open, onOpenChange, backend, onSubmit, isPending }: BackendFormProps) {
  const [name, setName] = useState('')
  const [type, setType] = useState<StorageBackendType>('nfs')
  const [nfsConfig, setNfsConfig] = useState<NfsConfig>(DEFAULT_NFS)
  const [iscsiConfig, setIscsiConfig] = useState<IscsiTargetConfig>(DEFAULT_ISCSI)
  const [s3Config, setS3Config] = useState<S3Config>(DEFAULT_S3)
  const [httpConfig, setHttpConfig] = useState<HttpConfig>(DEFAULT_HTTP)

  const isEditing = !!backend

  useEffect(() => {
    if (backend) {
      setName(backend.name)
      setType(backend.type)
      switch (backend.type) {
        case 'nfs':
          setNfsConfig(backend.config as NfsConfig)
          break
        case 'iscsi':
          setIscsiConfig(backend.config as IscsiTargetConfig)
          break
        case 's3':
          setS3Config(backend.config as S3Config)
          break
        case 'http':
          setHttpConfig(backend.config as HttpConfig)
          break
      }
    } else {
      setName('')
      setType('nfs')
      setNfsConfig(DEFAULT_NFS)
      setIscsiConfig(DEFAULT_ISCSI)
      setS3Config(DEFAULT_S3)
      setHttpConfig(DEFAULT_HTTP)
    }
  }, [backend, open])

  const handleSubmit = () => {
    let config
    switch (type) {
      case 'nfs':
        config = nfsConfig
        break
      case 'iscsi':
        config = iscsiConfig
        break
      case 's3':
        config = s3Config
        break
      case 'http':
        config = httpConfig
        break
    }
    onSubmit({ name, type, config })
  }

  const isValid = name.trim() !== ''

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEditing ? 'Edit Storage Backend' : 'Add Storage Backend'}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="name">Name</Label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., NFS - Primary"
            />
          </div>

          <div className="space-y-2">
            <Label>Type</Label>
            <Select value={type} onValueChange={(v) => setType(v as StorageBackendType)} disabled={isEditing}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(STORAGE_BACKEND_TYPE_LABELS).map(([value, label]) => (
                  <SelectItem key={value} value={value}>
                    {label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {type === 'nfs' && (
            <>
              <div className="space-y-2">
                <Label htmlFor="nfs-server">Server</Label>
                <Input
                  id="nfs-server"
                  value={nfsConfig.server}
                  onChange={(e) => setNfsConfig({ ...nfsConfig, server: e.target.value })}
                  placeholder="storage.local"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="nfs-path">Export Path</Label>
                <Input
                  id="nfs-path"
                  value={nfsConfig.export_path}
                  onChange={(e) => setNfsConfig({ ...nfsConfig, export_path: e.target.value })}
                  placeholder="/pureboot"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="nfs-options">Mount Options</Label>
                <Input
                  id="nfs-options"
                  value={nfsConfig.mount_options ?? ''}
                  onChange={(e) => setNfsConfig({ ...nfsConfig, mount_options: e.target.value })}
                  placeholder="vers=4.1,rsize=1048576"
                />
              </div>
            </>
          )}

          {type === 'iscsi' && (
            <>
              <div className="space-y-2">
                <Label htmlFor="iscsi-target">Target Address</Label>
                <Input
                  id="iscsi-target"
                  value={iscsiConfig.target}
                  onChange={(e) => setIscsiConfig({ ...iscsiConfig, target: e.target.value })}
                  placeholder="san.local"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="iscsi-port">Port</Label>
                <Input
                  id="iscsi-port"
                  type="number"
                  value={iscsiConfig.port}
                  onChange={(e) => setIscsiConfig({ ...iscsiConfig, port: parseInt(e.target.value) || 3260 })}
                />
              </div>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="iscsi-chap"
                  checked={iscsiConfig.chap_enabled}
                  onCheckedChange={(checked) => setIscsiConfig({ ...iscsiConfig, chap_enabled: !!checked })}
                />
                <Label htmlFor="iscsi-chap" className="font-normal">
                  Enable CHAP authentication
                </Label>
              </div>
            </>
          )}

          {type === 's3' && (
            <>
              <div className="space-y-2">
                <Label htmlFor="s3-endpoint">Endpoint URL</Label>
                <Input
                  id="s3-endpoint"
                  value={s3Config.endpoint}
                  onChange={(e) => setS3Config({ ...s3Config, endpoint: e.target.value })}
                  placeholder="https://s3.amazonaws.com"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="s3-bucket">Bucket</Label>
                <Input
                  id="s3-bucket"
                  value={s3Config.bucket}
                  onChange={(e) => setS3Config({ ...s3Config, bucket: e.target.value })}
                  placeholder="pureboot-images"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="s3-region">Region (optional)</Label>
                <Input
                  id="s3-region"
                  value={s3Config.region ?? ''}
                  onChange={(e) => setS3Config({ ...s3Config, region: e.target.value })}
                  placeholder="us-east-1"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="s3-access-key">Access Key ID</Label>
                <Input
                  id="s3-access-key"
                  value={s3Config.access_key_id}
                  onChange={(e) => setS3Config({ ...s3Config, access_key_id: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="s3-secret-key">Secret Access Key</Label>
                <Input
                  id="s3-secret-key"
                  type="password"
                  value={s3Config.secret_access_key ?? ''}
                  onChange={(e) => setS3Config({ ...s3Config, secret_access_key: e.target.value })}
                  placeholder={isEditing ? '(unchanged)' : ''}
                />
              </div>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="s3-cdn"
                  checked={s3Config.cdn_enabled}
                  onCheckedChange={(checked) => setS3Config({ ...s3Config, cdn_enabled: !!checked })}
                />
                <Label htmlFor="s3-cdn" className="font-normal">
                  Enable CDN
                </Label>
              </div>
              {s3Config.cdn_enabled && (
                <div className="space-y-2">
                  <Label htmlFor="s3-cdn-url">CDN URL</Label>
                  <Input
                    id="s3-cdn-url"
                    value={s3Config.cdn_url ?? ''}
                    onChange={(e) => setS3Config({ ...s3Config, cdn_url: e.target.value })}
                    placeholder="https://cdn.example.com"
                  />
                </div>
              )}
            </>
          )}

          {type === 'http' && (
            <>
              <div className="space-y-2">
                <Label htmlFor="http-url">Base URL</Label>
                <Input
                  id="http-url"
                  value={httpConfig.base_url}
                  onChange={(e) => setHttpConfig({ ...httpConfig, base_url: e.target.value })}
                  placeholder="https://files.example.com"
                />
              </div>
              <div className="space-y-2">
                <Label>Authentication</Label>
                <Select
                  value={httpConfig.auth_method}
                  onValueChange={(v) => setHttpConfig({ ...httpConfig, auth_method: v as 'none' | 'basic' | 'bearer' })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">None</SelectItem>
                    <SelectItem value="basic">Basic Auth</SelectItem>
                    <SelectItem value="bearer">Bearer Token</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {httpConfig.auth_method === 'basic' && (
                <>
                  <div className="space-y-2">
                    <Label htmlFor="http-username">Username</Label>
                    <Input
                      id="http-username"
                      value={httpConfig.username ?? ''}
                      onChange={(e) => setHttpConfig({ ...httpConfig, username: e.target.value })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="http-password">Password</Label>
                    <Input
                      id="http-password"
                      type="password"
                      value={httpConfig.password ?? ''}
                      onChange={(e) => setHttpConfig({ ...httpConfig, password: e.target.value })}
                      placeholder={isEditing ? '(unchanged)' : ''}
                    />
                  </div>
                </>
              )}
            </>
          )}
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
