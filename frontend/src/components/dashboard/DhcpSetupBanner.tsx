import { useState, useEffect } from 'react'
import { Copy, Check, ExternalLink, X, AlertTriangle, Rocket, ChevronDown, ChevronUp } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { systemApi, type DhcpStatusResponse } from '@/api'

const DISMISSED_KEY = 'pureboot-dhcp-banner-dismissed'

interface DhcpSetupBannerProps {
  onDismiss?: () => void
}

export function DhcpSetupBanner({ onDismiss }: DhcpSetupBannerProps) {
  const [dhcpStatus, setDhcpStatus] = useState<DhcpStatusResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState<string | null>(null)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [dismissed, setDismissed] = useState(() => {
    return localStorage.getItem(DISMISSED_KEY) === 'true'
  })

  useEffect(() => {
    loadDhcpStatus()
  }, [])

  async function loadDhcpStatus() {
    try {
      setLoading(true)
      const status = await systemApi.getDhcpStatus()
      setDhcpStatus(status)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load DHCP status')
    } finally {
      setLoading(false)
    }
  }

  function handleDismiss() {
    localStorage.setItem(DISMISSED_KEY, 'true')
    setDismissed(true)
    onDismiss?.()
  }

  async function copyToClipboard(text: string, key: string) {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(key)
      setTimeout(() => setCopied(null), 2000)
    } catch {
      const textarea = document.createElement('textarea')
      textarea.value = text
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
      setCopied(key)
      setTimeout(() => setCopied(null), 2000)
    }
  }

  if (loading || error || dismissed || !dhcpStatus) {
    return null
  }

  const { server_ip, required_settings, status, first_run } = dhcpStatus
  const hasIssues = status.nodes_with_issues > 0

  if (!first_run && !hasIssues) {
    return null
  }

  // Full ISC DHCP config with architecture detection (recommended for mixed environments)
  const iscDhcpConfig = `# PureBoot PXE Configuration (Mixed BIOS + UEFI)
# Add to your dhcpd.conf - RECOMMENDED for homelabs with mixed hardware

# Define architecture option (required for BIOS/UEFI detection)
option arch code 93 = unsigned integer 16;

# PXE boot settings - point to PureBoot server
next-server ${server_ip};

# Dynamically serve correct bootloader based on client architecture
# Client sends Option 93 indicating what it supports
if option arch = 00:00 {
    filename "${required_settings.filename_bios}";      # BIOS x86
} elsif option arch = 00:06 {
    filename "${required_settings.filename_uefi}";      # UEFI x86 (32-bit)
} elsif option arch = 00:07 {
    filename "${required_settings.filename_uefi}";      # UEFI x64 (most common)
} elsif option arch = 00:09 {
    filename "${required_settings.filename_uefi}";      # UEFI x64 EBC
} elsif option arch = 00:0b {
    filename "uefi/arm64.efi";                          # ARM64 UEFI
} else {
    filename "${required_settings.filename_bios}";      # Fallback to BIOS
}`

  // dnsmasq config (common for home routers, Pi-hole)
  const dnsmasqConfig = `# PureBoot PXE Configuration for dnsmasq
# Add to /etc/dnsmasq.conf or /etc/dnsmasq.d/pxe.conf

# Enable TFTP and set root
enable-tftp
tftp-root=/var/lib/tftpboot

# Tag clients by architecture (Option 93)
dhcp-match=set:bios,option:client-arch,0
dhcp-match=set:efi32,option:client-arch,6
dhcp-match=set:efi64,option:client-arch,7
dhcp-match=set:efi64,option:client-arch,9

# Serve appropriate bootloader
dhcp-boot=tag:bios,${required_settings.filename_bios},pureboot,${server_ip}
dhcp-boot=tag:efi32,${required_settings.filename_uefi},pureboot,${server_ip}
dhcp-boot=tag:efi64,${required_settings.filename_uefi},pureboot,${server_ip}

# Default fallback
dhcp-boot=${required_settings.filename_bios},pureboot,${server_ip}`

  // Simple config (BIOS only)
  const simpleBiosConfig = `next-server ${server_ip};
filename "${required_settings.filename_bios}";`

  // Simple config (UEFI only)
  const simpleUefiConfig = `next-server ${server_ip};
filename "${required_settings.filename_uefi}";`

  if (first_run) {
    return (
      <Card className="mb-6 border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-950">
        <CardContent className="p-4">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className="rounded-full bg-blue-100 p-2 dark:bg-blue-900">
                <Rocket className="h-5 w-5 text-blue-600 dark:text-blue-400" />
              </div>
              <div className="flex-1">
                <h3 className="font-semibold text-blue-900 dark:text-blue-100">
                  Getting Started with PureBoot
                </h3>
                <p className="mt-1 text-sm text-blue-700 dark:text-blue-300">
                  Configure your DHCP server to enable PXE boot. Your DHCP server tells booting
                  clients where to find the bootloader.
                </p>

                {/* Required Options Explanation */}
                <div className="mt-4 rounded-md bg-white p-3 dark:bg-blue-900/50">
                  <h4 className="text-sm font-medium text-blue-900 dark:text-blue-100 mb-2">
                    Required DHCP Options
                  </h4>
                  <div className="space-y-2 text-sm">
                    <OptionRow
                      option="66"
                      name="next-server"
                      value={server_ip}
                      description="TFTP server IP - where to download boot files"
                      copied={copied === 'opt66'}
                      onCopy={() => copyToClipboard(server_ip, 'opt66')}
                    />
                    <OptionRow
                      option="67"
                      name="filename"
                      value={required_settings.filename_bios}
                      description="Boot file path - which bootloader to load"
                      copied={copied === 'opt67'}
                      onCopy={() => copyToClipboard(required_settings.filename_bios, 'opt67')}
                    />
                  </div>
                </div>

                {/* Architecture Detection */}
                <div className="mt-3 rounded-md bg-white p-3 dark:bg-blue-900/50">
                  <h4 className="text-sm font-medium text-blue-900 dark:text-blue-100 mb-2">
                    BIOS vs UEFI Detection (Option 93)
                  </h4>
                  <p className="text-xs text-blue-600 dark:text-blue-400 mb-2">
                    Clients send Option 93 to indicate their architecture. Your DHCP server
                    should respond with the correct bootloader:
                  </p>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="rounded bg-blue-100 p-2 dark:bg-blue-800">
                      <div className="font-medium">BIOS (arch = 0x00)</div>
                      <code className="text-blue-700 dark:text-blue-300">{required_settings.filename_bios}</code>
                    </div>
                    <div className="rounded bg-blue-100 p-2 dark:bg-blue-800">
                      <div className="font-medium">UEFI x64 (arch = 0x07, 0x09)</div>
                      <code className="text-blue-700 dark:text-blue-300">{required_settings.filename_uefi}</code>
                    </div>
                  </div>
                </div>

                {/* Copy Config Buttons - Recommended first */}
                <div className="mt-4 space-y-3">
                  {/* Recommended: Dynamic/Mixed */}
                  <div className="rounded-md border border-green-300 bg-green-50 p-3 dark:border-green-700 dark:bg-green-900/30">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium text-green-800 dark:text-green-200">
                        Recommended: Dynamic Config (Mixed BIOS + UEFI)
                      </span>
                      <span className="text-xs bg-green-200 text-green-800 px-2 py-0.5 rounded dark:bg-green-800 dark:text-green-200">
                        Homelab
                      </span>
                    </div>
                    <p className="text-xs text-green-700 dark:text-green-300 mb-2">
                      Automatically detects client architecture and serves the correct bootloader.
                    </p>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        className="border-green-400 text-green-700 hover:bg-green-100 dark:border-green-600 dark:text-green-300 dark:hover:bg-green-900"
                        onClick={() => copyToClipboard(iscDhcpConfig, 'isc')}
                      >
                        {copied === 'isc' ? (
                          <><Check className="mr-1.5 h-4 w-4" />Copied!</>
                        ) : (
                          <><Copy className="mr-1.5 h-4 w-4" />ISC DHCP (dhcpd)</>
                        )}
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="border-green-400 text-green-700 hover:bg-green-100 dark:border-green-600 dark:text-green-300 dark:hover:bg-green-900"
                        onClick={() => copyToClipboard(dnsmasqConfig, 'dnsmasq')}
                      >
                        {copied === 'dnsmasq' ? (
                          <><Check className="mr-1.5 h-4 w-4" />Copied!</>
                        ) : (
                          <><Copy className="mr-1.5 h-4 w-4" />dnsmasq (Pi-hole)</>
                        )}
                      </Button>
                    </div>
                  </div>

                  {/* Simple configs for single-arch environments */}
                  <div className="flex flex-wrap gap-2">
                    <span className="text-xs text-blue-600 dark:text-blue-400 w-full mb-1">
                      Or for single-architecture environments:
                    </span>
                    <Button
                      variant="outline"
                      size="sm"
                      className="border-blue-300 text-blue-700 hover:bg-blue-100 dark:border-blue-700 dark:text-blue-300 dark:hover:bg-blue-900"
                      onClick={() => copyToClipboard(simpleBiosConfig, 'bios')}
                    >
                      {copied === 'bios' ? (
                        <><Check className="mr-1.5 h-4 w-4" />Copied!</>
                      ) : (
                        <><Copy className="mr-1.5 h-4 w-4" />BIOS Only</>
                      )}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="border-blue-300 text-blue-700 hover:bg-blue-100 dark:border-blue-700 dark:text-blue-300 dark:hover:bg-blue-900"
                      onClick={() => copyToClipboard(simpleUefiConfig, 'uefi')}
                    >
                      {copied === 'uefi' ? (
                        <><Check className="mr-1.5 h-4 w-4" />Copied!</>
                      ) : (
                        <><Copy className="mr-1.5 h-4 w-4" />UEFI Only</>
                      )}
                    </Button>
                  </div>
                </div>

                {/* Expandable full configs */}
                <div className="mt-3">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-blue-700 hover:bg-blue-100 dark:text-blue-300 dark:hover:bg-blue-900 w-full justify-start"
                    onClick={() => setShowAdvanced(!showAdvanced)}
                  >
                    {showAdvanced ? (
                      <><ChevronUp className="mr-1.5 h-4 w-4" />Hide full configuration examples</>
                    ) : (
                      <><ChevronDown className="mr-1.5 h-4 w-4" />Show full configuration examples</>
                    )}
                  </Button>
                </div>

                {showAdvanced && (
                  <div className="mt-3 space-y-4">
                    {/* ISC DHCP */}
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-medium text-blue-800 dark:text-blue-200">ISC DHCP Server (dhcpd.conf)</span>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 text-xs text-blue-500 hover:bg-blue-100 dark:hover:bg-blue-900"
                          onClick={() => copyToClipboard(iscDhcpConfig, 'isc-full')}
                        >
                          {copied === 'isc-full' ? <><Check className="mr-1 h-3 w-3" />Copied</> : <><Copy className="mr-1 h-3 w-3" />Copy</>}
                        </Button>
                      </div>
                      <pre className="rounded-md bg-slate-900 p-3 text-xs text-slate-100 overflow-x-auto max-h-48">
                        {iscDhcpConfig}
                      </pre>
                    </div>

                    {/* dnsmasq */}
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-medium text-blue-800 dark:text-blue-200">dnsmasq (Pi-hole, OpenWrt, etc.)</span>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 text-xs text-blue-500 hover:bg-blue-100 dark:hover:bg-blue-900"
                          onClick={() => copyToClipboard(dnsmasqConfig, 'dnsmasq-full')}
                        >
                          {copied === 'dnsmasq-full' ? <><Check className="mr-1 h-3 w-3" />Copied</> : <><Copy className="mr-1 h-3 w-3" />Copy</>}
                        </Button>
                      </div>
                      <pre className="rounded-md bg-slate-900 p-3 text-xs text-slate-100 overflow-x-auto max-h-48">
                        {dnsmasqConfig}
                      </pre>
                    </div>
                  </div>
                )}

                <div className="mt-4">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-blue-700 hover:bg-blue-100 dark:text-blue-300 dark:hover:bg-blue-900"
                    asChild
                  >
                    <a
                      href="https://github.com/mrveiss/pureboot/blob/main/docs/guides/dhcp-configuration.md"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <ExternalLink className="mr-1.5 h-4 w-4" />
                      View Full DHCP Guide (dnsmasq, MikroTik, Windows, etc.)
                    </a>
                  </Button>
                </div>
              </div>
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 shrink-0 text-blue-500 hover:bg-blue-100 hover:text-blue-700 dark:hover:bg-blue-900"
              onClick={handleDismiss}
            >
              <X className="h-4 w-4" />
              <span className="sr-only">Dismiss</span>
            </Button>
          </div>
        </CardContent>
      </Card>
    )
  }

  // Warning banner for DHCP issues
  return (
    <Card className="mb-6 border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950">
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="rounded-full bg-amber-100 p-2 dark:bg-amber-900">
              <AlertTriangle className="h-5 w-5 text-amber-600 dark:text-amber-400" />
            </div>
            <div className="flex-1">
              <h3 className="font-semibold text-amber-900 dark:text-amber-100">
                DHCP Configuration Issue
              </h3>
              <p className="mt-1 text-sm text-amber-700 dark:text-amber-300">
                {status.nodes_with_issues} node{status.nodes_with_issues !== 1 ? 's' : ''} received
                incorrect DHCP settings.
              </p>

              {status.issues.length > 0 && (
                <ul className="mt-2 space-y-1 text-sm text-amber-700 dark:text-amber-300">
                  {status.issues.map((issue, idx) => (
                    <li key={idx}>
                      {issue.type === 'wrong_next_server' && (
                        <>
                          Option 66 (next-server) points to{' '}
                          <code className="rounded bg-amber-200 px-1 dark:bg-amber-800">{issue.received}</code>
                          {' '}instead of{' '}
                          <code className="rounded bg-amber-200 px-1 dark:bg-amber-800">{issue.expected}</code>
                        </>
                      )}
                      {issue.type === 'wrong_filename' && (
                        <>
                          Option 67 (filename) is incorrect - check BIOS/UEFI bootloader path
                        </>
                      )}
                    </li>
                  ))}
                </ul>
              )}

              <div className="mt-4 flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="border-amber-300 text-amber-700 hover:bg-amber-100 dark:border-amber-700 dark:text-amber-300 dark:hover:bg-amber-900"
                  asChild
                >
                  <a
                    href="https://github.com/mrveiss/pureboot/blob/main/docs/guides/dhcp-configuration.md"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <ExternalLink className="mr-1.5 h-4 w-4" />
                    Fix DHCP Settings
                  </a>
                </Button>
              </div>
            </div>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0 text-amber-500 hover:bg-amber-100 hover:text-amber-700 dark:hover:bg-amber-900"
            onClick={handleDismiss}
          >
            <X className="h-4 w-4" />
            <span className="sr-only">Dismiss</span>
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

interface OptionRowProps {
  option: string
  name: string
  value: string
  description: string
  copied: boolean
  onCopy: () => void
}

function OptionRow({ option, name, value, description, copied, onCopy }: OptionRowProps) {
  return (
    <div className="flex items-start gap-2">
      <div className="flex-shrink-0 w-16">
        <span className="inline-block rounded bg-blue-200 px-1.5 py-0.5 text-xs font-medium text-blue-800 dark:bg-blue-700 dark:text-blue-100">
          Opt {option}
        </span>
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium text-blue-900 dark:text-blue-100">{name}:</span>
          <code className="rounded bg-blue-100 px-1.5 py-0.5 font-mono text-xs dark:bg-blue-800">
            {value}
          </code>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 text-blue-500 hover:bg-blue-200 dark:hover:bg-blue-700"
            onClick={onCopy}
          >
            {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
          </Button>
        </div>
        <p className="text-xs text-blue-600 dark:text-blue-400 mt-0.5">{description}</p>
      </div>
    </div>
  )
}
