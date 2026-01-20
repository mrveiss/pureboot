import { Bell, Moon, Sun, LogOut, User } from 'lucide-react'
import { Button } from '@/components/ui'
import { useAuthStore, useThemeStore } from '@/stores'

interface HeaderProps {
  notificationCount?: number
}

export function Header({ notificationCount = 0 }: HeaderProps) {
  const { user, logout } = useAuthStore()
  const { theme, setTheme, resolvedTheme } = useThemeStore()

  const toggleTheme = () => {
    if (theme === 'system') {
      setTheme(resolvedTheme === 'dark' ? 'light' : 'dark')
    } else {
      setTheme(theme === 'dark' ? 'light' : 'dark')
    }
  }

  return (
    <header className="flex h-16 items-center justify-between border-b bg-card px-6">
      <div className="flex items-center gap-4">
        <h1 className="text-lg font-semibold">Node Lifecycle Management</h1>
      </div>

      <div className="flex items-center gap-2">
        <Button variant="ghost" size="icon" className="relative" aria-label="Notifications">
          <Bell className="h-5 w-5" />
          {notificationCount > 0 && (
            <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-destructive px-1 text-xs text-destructive-foreground">
              {notificationCount > 99 ? '99+' : notificationCount}
            </span>
          )}
        </Button>

        <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label="Toggle theme">
          {resolvedTheme === 'dark' ? (
            <Sun className="h-5 w-5" />
          ) : (
            <Moon className="h-5 w-5" />
          )}
        </Button>

        <div className="ml-2 flex items-center gap-2 border-l pl-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-primary-foreground">
            <User className="h-4 w-4" />
          </div>
          <div className="hidden flex-col sm:flex">
            <span className="text-sm font-medium">{user?.name || 'User'}</span>
            <span className="text-xs text-muted-foreground">{user?.role || 'Unknown'}</span>
          </div>
          <Button variant="ghost" size="icon" onClick={() => logout()} aria-label="Logout">
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </header>
  )
}
