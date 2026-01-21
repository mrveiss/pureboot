import { createBrowserRouter, Navigate } from 'react-router-dom'
import { AppShell } from '@/components/layout'
import { Dashboard, Nodes, NodeDetail, Groups, GroupDetail, Storage, NotFound } from '@/pages'

// Authentication is not yet implemented on the backend
// All routes are currently open access (secure with firewall)
// TODO: Re-enable ProtectedRoute when backend auth is implemented

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <Navigate to="/" replace />,
  },
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: 'nodes', element: <Nodes /> },
      { path: 'nodes/:nodeId', element: <NodeDetail /> },
      { path: 'groups', element: <Groups /> },
      { path: 'groups/:groupId', element: <GroupDetail /> },
      { path: 'workflows', element: <div>Workflows (Coming Soon)</div> },
      { path: 'templates', element: <div>Templates (Coming Soon)</div> },
      { path: 'hypervisors', element: <div>Hypervisors (Coming Soon)</div> },
      { path: 'storage', element: <Storage /> },
      { path: 'approvals', element: <div>Approvals (Coming Soon)</div> },
      { path: 'activity', element: <div>Activity Log (Coming Soon)</div> },
      { path: 'settings', element: <div>Settings (Coming Soon)</div> },
      { path: 'users', element: <div>Users & Roles (Coming Soon)</div> },
      { path: '*', element: <NotFound /> },
    ],
  },
])
