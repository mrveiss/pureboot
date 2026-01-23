export interface Template {
  id: string
  name: string
  type: TemplateType
  os_family: string | null
  os_name: string | null
  os_version: string | null
  architecture: string
  file_path: string | null
  storage_backend_id: string | null
  storage_backend_name: string | null
  size_bytes: number | null
  checksum: string | null
  description: string | null
  created_at: string
  updated_at: string
}

export type TemplateType = 'iso' | 'kickstart' | 'preseed' | 'autounattend' | 'cloud-init' | 'script'

export const TEMPLATE_TYPE_LABELS: Record<TemplateType, string> = {
  iso: 'ISO Image',
  kickstart: 'Kickstart (RHEL/Fedora)',
  preseed: 'Preseed (Debian/Ubuntu)',
  autounattend: 'Autounattend (Windows)',
  'cloud-init': 'Cloud-Init',
  script: 'Script',
}

export const TEMPLATE_TYPE_ICONS: Record<TemplateType, string> = {
  iso: 'disc',
  kickstart: 'file-code',
  preseed: 'file-code',
  autounattend: 'file-code',
  'cloud-init': 'cloud',
  script: 'terminal',
}

export const OS_FAMILY_LABELS: Record<string, string> = {
  linux: 'Linux',
  windows: 'Windows',
  bsd: 'BSD',
}
