import { NavLink } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { Separator } from '@/components/ui'
import {
  LayoutDashboard,
  Server,
  Folders,
  Workflow,
  FileCode,
  HardDrive,
  Cloud,
  ClipboardCheck,
  Activity,
  Settings,
  Users,
  Copy,
} from 'lucide-react'

interface NavItemProps {
  to: string
  icon: React.ReactNode
  label: string
  badge?: number
}

function NavItem({ to, icon, label, badge }: NavItemProps) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cn(
          'flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
          isActive
            ? 'bg-accent text-accent-foreground'
            : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
        )
      }
    >
      {icon}
      <span className="flex-1">{label}</span>
      {badge !== undefined && badge > 0 && (
        <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-xs text-primary-foreground">
          {badge}
        </span>
      )}
    </NavLink>
  )
}

interface SidebarProps {
  pendingApprovals?: number
}

export function Sidebar({ pendingApprovals = 0 }: SidebarProps) {
  return (
    <aside className="flex h-full w-64 flex-col border-r bg-card">
      <div className="flex h-16 items-center gap-2 border-b px-4">
        <img src="/pureboot-logo.png" alt="PureBoot" className="h-8 w-8" />
        <span className="text-lg font-semibold">PureBoot</span>
      </div>

      <nav className="flex-1 space-y-1 p-4">
        <NavItem to="/" icon={<LayoutDashboard className="h-4 w-4" />} label="Dashboard" />
        <NavItem to="/nodes" icon={<Server className="h-4 w-4" />} label="Nodes" />
        <NavItem to="/groups" icon={<Folders className="h-4 w-4" />} label="Device Groups" />
        <NavItem to="/workflows" icon={<Workflow className="h-4 w-4" />} label="Workflows" />
        <NavItem to="/templates" icon={<FileCode className="h-4 w-4" />} label="Templates" />
        <NavItem to="/hypervisors" icon={<Cloud className="h-4 w-4" />} label="Hypervisors" />
        <NavItem to="/storage" icon={<HardDrive className="h-4 w-4" />} label="Storage" />
        <NavItem to="/clone" icon={<Copy className="h-4 w-4" />} label="Clone Sessions" />

        <Separator className="my-4" />

        <NavItem
          to="/approvals"
          icon={<ClipboardCheck className="h-4 w-4" />}
          label="Approvals"
          badge={pendingApprovals}
        />
        <NavItem to="/activity" icon={<Activity className="h-4 w-4" />} label="Activity Log" />

        <Separator className="my-4" />

        <NavItem to="/settings" icon={<Settings className="h-4 w-4" />} label="Settings" />
        <NavItem to="/users" icon={<Users className="h-4 w-4" />} label="Users & Roles" />
      </nav>
    </aside>
  )
}
