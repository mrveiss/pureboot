import { useState, useEffect } from 'react'
import { Copy, Check, ExternalLink, X, AlertTriangle, Rocket } from 'lucide-react'
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
      // Fallback for older browsers
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

  // Show setup banner on first run, or warning banner if there are issues
  if (!first_run && !hasIssues) {
    return null
  }

  // First run setup banner
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
                  Configure your DHCP server with these settings to enable PXE boot:
                </p>

                <div className="mt-4 space-y-3">
                  <SettingRow
                    label="Option 66 (next-server)"
                    value={required_settings.next_server}
                    copied={copied === 'next_server'}
                    onCopy={() => copyToClipboard(required_settings.next_server, 'next_server')}
                  />
                  <SettingRow
                    label="Option 67 - BIOS (filename)"
                    value={required_settings.filename_bios}
                    copied={copied === 'filename_bios'}
                    onCopy={() => copyToClipboard(required_settings.filename_bios, 'filename_bios')}
                  />
                  <SettingRow
                    label="Option 67 - UEFI (filename)"
                    value={required_settings.filename_uefi}
                    copied={copied === 'filename_uefi'}
                    onCopy={() => copyToClipboard(required_settings.filename_uefi, 'filename_uefi')}
                  />
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="border-blue-300 text-blue-700 hover:bg-blue-100 dark:border-blue-700 dark:text-blue-300 dark:hover:bg-blue-900"
                    onClick={() => copyToClipboard(
                      `next-server ${server_ip};\nfilename "${required_settings.filename_bios}";`,
                      'all'
                    )}
                  >
                    {copied === 'all' ? (
                      <>
                        <Check className="mr-1.5 h-4 w-4" />
                        Copied!
                      </>
                    ) : (
                      <>
                        <Copy className="mr-1.5 h-4 w-4" />
                        Copy ISC DHCP Config
                      </>
                    )}
                  </Button>
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
                      View DHCP Guide
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
                          next-server points to <code className="rounded bg-amber-200 px-1 dark:bg-amber-800">{issue.received}</code>
                          {' '}instead of <code className="rounded bg-amber-200 px-1 dark:bg-amber-800">{issue.expected}</code>
                        </>
                      )}
                      {issue.type === 'wrong_filename' && (
                        <>
                          Wrong bootloader filename received
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

interface SettingRowProps {
  label: string
  value: string
  copied: boolean
  onCopy: () => void
}

function SettingRow({ label, value, copied, onCopy }: SettingRowProps) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-sm text-blue-600 dark:text-blue-400 min-w-[180px]">
        {label}:
      </span>
      <code className="flex-1 rounded bg-white px-2 py-1 font-mono text-sm dark:bg-blue-900">
        {value}
      </code>
      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8 text-blue-500 hover:bg-blue-100 hover:text-blue-700 dark:hover:bg-blue-900"
        onClick={onCopy}
      >
        {copied ? (
          <Check className="h-4 w-4" />
        ) : (
          <Copy className="h-4 w-4" />
        )}
        <span className="sr-only">Copy</span>
      </Button>
    </div>
  )
}
