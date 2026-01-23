import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import {
  Settings as SettingsIcon,
  Network,
  RotateCcw,
  Check,
  Server,
  Palette,
  Info,
  Monitor,
  Moon,
  Sun,
  RefreshCw,
  Wifi,
  HardDrive,
} from 'lucide-react'
import { DHCP_BANNER_DISMISSED_KEY } from '@/components/dashboard'
import { useThemeStore } from '@/stores'
import { apiClient } from '@/api/client'

interface ServerInfo {
  version: string
  server_ip: string
  http_port: number
  tftp_enabled: boolean
  tftp_port: number
  dhcp_proxy_enabled: boolean
  dhcp_proxy_port: number
}

export function Settings() {
  const [dhcpBannerDismissed, setDhcpBannerDismissed] = useState(() => {
    return localStorage.getItem(DHCP_BANNER_DISMISSED_KEY) === 'true'
  })
  const [resetSuccess, setResetSuccess] = useState(false)
  const [serverInfo, setServerInfo] = useState<ServerInfo | null>(null)
  const [serverInfoLoading, setServerInfoLoading] = useState(true)

  const { theme, setTheme } = useThemeStore()

  useEffect(() => {
    async function fetchServerInfo() {
      try {
        const info = await apiClient.get<ServerInfo>('/system/info')
        setServerInfo(info)
      } catch (error) {
        console.error('Failed to fetch server info:', error)
      } finally {
        setServerInfoLoading(false)
      }
    }
    fetchServerInfo()
  }, [])

  function handleResetDhcpBanner() {
    localStorage.removeItem(DHCP_BANNER_DISMISSED_KEY)
    setDhcpBannerDismissed(false)
    setResetSuccess(true)
    setTimeout(() => setResetSuccess(false), 2000)
  }

  async function handleRefreshServerInfo() {
    setServerInfoLoading(true)
    try {
      const info = await apiClient.get<ServerInfo>('/system/info')
      setServerInfo(info)
    } catch (error) {
      console.error('Failed to fetch server info:', error)
    } finally {
      setServerInfoLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <SettingsIcon className="h-8 w-8 text-muted-foreground" />
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Settings</h2>
          <p className="text-muted-foreground">Configure PureBoot preferences</p>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {/* Server Information */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Server className="h-5 w-5" />
                <CardTitle>Server Information</CardTitle>
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={handleRefreshServerInfo}
                disabled={serverInfoLoading}
              >
                <RefreshCw className={serverInfoLoading ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} />
              </Button>
            </div>
            <CardDescription>
              Current server configuration and status
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {serverInfoLoading && !serverInfo ? (
              <div className="text-sm text-muted-foreground">Loading...</div>
            ) : serverInfo ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-sm">
                    <Info className="h-4 w-4 text-muted-foreground" />
                    <span className="text-muted-foreground">Version</span>
                  </div>
                  <Badge variant="secondary">{serverInfo.version}</Badge>
                </div>

                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-sm">
                    <Wifi className="h-4 w-4 text-muted-foreground" />
                    <span className="text-muted-foreground">Server IP</span>
                  </div>
                  <span className="text-sm font-mono">{serverInfo.server_ip}</span>
                </div>

                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-sm">
                    <Monitor className="h-4 w-4 text-muted-foreground" />
                    <span className="text-muted-foreground">HTTP Port</span>
                  </div>
                  <span className="text-sm font-mono">{serverInfo.http_port}</span>
                </div>

                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-sm">
                    <HardDrive className="h-4 w-4 text-muted-foreground" />
                    <span className="text-muted-foreground">TFTP Server</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={serverInfo.tftp_enabled ? 'default' : 'secondary'}>
                      {serverInfo.tftp_enabled ? 'Enabled' : 'Disabled'}
                    </Badge>
                    {serverInfo.tftp_enabled && (
                      <span className="text-sm text-muted-foreground">:{serverInfo.tftp_port}</span>
                    )}
                  </div>
                </div>

                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-sm">
                    <Network className="h-4 w-4 text-muted-foreground" />
                    <span className="text-muted-foreground">Proxy DHCP</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={serverInfo.dhcp_proxy_enabled ? 'default' : 'secondary'}>
                      {serverInfo.dhcp_proxy_enabled ? 'Enabled' : 'Disabled'}
                    </Badge>
                    {serverInfo.dhcp_proxy_enabled && (
                      <span className="text-sm text-muted-foreground">:{serverInfo.dhcp_proxy_port}</span>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-sm text-muted-foreground">Failed to load server info</div>
            )}
          </CardContent>
        </Card>

        {/* Theme Settings */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Palette className="h-5 w-5" />
              <CardTitle>Appearance</CardTitle>
            </div>
            <CardDescription>
              Customize the look and feel of the interface
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>Theme</Label>
              <Select value={theme} onValueChange={(v) => setTheme(v as 'light' | 'dark' | 'system')}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="light">
                    <div className="flex items-center gap-2">
                      <Sun className="h-4 w-4" />
                      Light
                    </div>
                  </SelectItem>
                  <SelectItem value="dark">
                    <div className="flex items-center gap-2">
                      <Moon className="h-4 w-4" />
                      Dark
                    </div>
                  </SelectItem>
                  <SelectItem value="system">
                    <div className="flex items-center gap-2">
                      <Monitor className="h-4 w-4" />
                      System
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Choose between light, dark, or system preference
              </p>
            </div>
          </CardContent>
        </Card>

        {/* DHCP Configuration Section */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Network className="h-5 w-5" />
              <CardTitle>DHCP Configuration</CardTitle>
            </div>
            <CardDescription>
              Manage DHCP setup wizard and network boot configuration
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between rounded-lg border p-4">
              <div className="space-y-1">
                <p className="font-medium">DHCP Setup Guide</p>
                <p className="text-sm text-muted-foreground">
                  {dhcpBannerDismissed
                    ? 'The setup guide is currently hidden.'
                    : 'The setup guide is visible on the Dashboard.'}
                </p>
              </div>
              <Button
                variant="outline"
                onClick={handleResetDhcpBanner}
                disabled={!dhcpBannerDismissed || resetSuccess}
              >
                {resetSuccess ? (
                  <>
                    <Check className="mr-2 h-4 w-4" />
                    Done
                  </>
                ) : (
                  <>
                    <RotateCcw className="mr-2 h-4 w-4" />
                    Show Guide
                  </>
                )}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* About Section */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Info className="h-5 w-5" />
              <CardTitle>About PureBoot</CardTitle>
            </div>
            <CardDescription>
              Unified vendor-neutral node lifecycle platform
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              PureBoot is a self-hosted platform for automated provisioning of bare-metal servers,
              VMs, Raspberry Pi, and enterprise devices. It replaces manual PXE setups with a
              unified state-based automation layer.
            </p>
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline">MIT License</Badge>
              <Badge variant="outline">FastAPI Backend</Badge>
              <Badge variant="outline">React Frontend</Badge>
            </div>
            <div className="pt-2 border-t">
              <a
                href="https://github.com/mrveiss/pureboot"
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-primary hover:underline"
              >
                View on GitHub
              </a>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
