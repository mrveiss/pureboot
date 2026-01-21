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

  // Full ISC DHCP config with architecture detection
  const iscDhcpConfig = `# PureBoot PXE Configuration
# Add to your dhcpd.conf

# Define architecture option (required for BIOS/UEFI detection)
option arch code 93 = unsigned integer 16;

# PXE boot settings
next-server ${server_ip};

# Serve different bootloaders based on client architecture
if option arch = 00:00 {
    filename "${required_settings.filename_bios}";      # BIOS x86
} elsif option arch = 00:07 {
    filename "${required_settings.filename_uefi}";      # UEFI x64
} elsif option arch = 00:09 {
    filename "${required_settings.filename_uefi}";      # UEFI x64 (EBC)
} else {
    filename "${required_settings.filename_bios}";      # Fallback to BIOS
}`

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

                {/* Quick Copy Buttons */}
                <div className="mt-4 flex flex-wrap gap-2">
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
                  <Button
                    variant="outline"
                    size="sm"
                    className="border-blue-300 text-blue-700 hover:bg-blue-100 dark:border-blue-700 dark:text-blue-300 dark:hover:bg-blue-900"
                    onClick={() => setShowAdvanced(!showAdvanced)}
                  >
                    {showAdvanced ? (
                      <><ChevronUp className="mr-1.5 h-4 w-4" />Hide Full Config</>
                    ) : (
                      <><ChevronDown className="mr-1.5 h-4 w-4" />Full ISC DHCP Config</>
                    )}
                  </Button>
                </div>

                {/* Full Config (Expandable) */}
                {showAdvanced && (
                  <div className="mt-3">
                    <div className="relative">
                      <pre className="rounded-md bg-slate-900 p-3 text-xs text-slate-100 overflow-x-auto">
                        {iscDhcpConfig}
                      </pre>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="absolute top-2 right-2 h-7 text-slate-400 hover:text-white hover:bg-slate-700"
                        onClick={() => copyToClipboard(iscDhcpConfig, 'full')}
                      >
                        {copied === 'full' ? (
                          <><Check className="mr-1 h-3 w-3" />Copied</>
                        ) : (
                          <><Copy className="mr-1 h-3 w-3" />Copy</>
                        )}
                      </Button>
                    </div>
                    <p className="mt-2 text-xs text-blue-600 dark:text-blue-400">
                      This config automatically serves the correct bootloader based on client architecture.
                    </p>
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
