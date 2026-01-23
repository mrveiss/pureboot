import { createBrowserRouter, Navigate } from 'react-router-dom'
import { AppShell } from '@/components/layout'
import { Dashboard, Nodes, NodeDetail, Groups, GroupDetail, Workflows, Templates, Hypervisors, ActivityLog, Approvals, Users, Storage, CloneSessions, CloneDetail, Settings, NotFound } from '@/pages'

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
      { path: 'workflows', element: <Workflows /> },
      { path: 'templates', element: <Templates /> },
      { path: 'hypervisors', element: <Hypervisors /> },
      { path: 'storage', element: <Storage /> },
      { path: 'clone', element: <CloneSessions /> },
      { path: 'clone/:id', element: <CloneDetail /> },
      { path: 'approvals', element: <Approvals /> },
      { path: 'activity', element: <ActivityLog /> },
      { path: 'settings', element: <Settings /> },
      { path: 'users', element: <Users /> },
      { path: '*', element: <NotFound /> },
    ],
  },
])
