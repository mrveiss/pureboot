export interface Workflow {
  id: string
  name: string
  kernel_path: string
  initrd_path: string
  cmdline: string
  architecture: 'x86_64' | 'aarch64' | 'armv7l'
  boot_mode: 'bios' | 'uefi'
}

export const ARCHITECTURE_LABELS: Record<string, string> = {
  x86_64: 'x86_64 (64-bit)',
  aarch64: 'ARM64 (aarch64)',
  armv7l: 'ARM32 (armv7l)',
}

export const BOOT_MODE_LABELS: Record<string, string> = {
  bios: 'BIOS (Legacy)',
  uefi: 'UEFI',
}
