import { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Settings as SettingsIcon, Network, RotateCcw, Check } from 'lucide-react'
import { DHCP_BANNER_DISMISSED_KEY } from '@/components/dashboard'

export function Settings() {
  const [dhcpBannerDismissed, setDhcpBannerDismissed] = useState(() => {
    return localStorage.getItem(DHCP_BANNER_DISMISSED_KEY) === 'true'
  })
  const [resetSuccess, setResetSuccess] = useState(false)

  function handleResetDhcpBanner() {
    localStorage.removeItem(DHCP_BANNER_DISMISSED_KEY)
    setDhcpBannerDismissed(false)
    setResetSuccess(true)
    setTimeout(() => setResetSuccess(false), 2000)
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

      <div className="grid gap-6">
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
                    ? 'The setup guide is currently hidden. Reset to show it again on the Dashboard.'
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
                    Show Guide Again
                  </>
                )}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Placeholder for future settings */}
        <Card>
          <CardHeader>
            <CardTitle>More Settings Coming Soon</CardTitle>
            <CardDescription>
              Additional configuration options will be available in future updates
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Planned settings include: authentication, TFTP server configuration,
              proxy DHCP settings, notification preferences, and more.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
