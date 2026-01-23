import { createBrowserRouter } from 'react-router-dom'
import { AppShell } from '@/components/layout'
import { ProtectedRoute } from '@/components/ProtectedRoute'
import { Dashboard, Nodes, NodeDetail, Groups, GroupDetail, Workflows, Templates, Hypervisors, ActivityLog, Approvals, Users, Storage, Settings, Login, NotFound } from '@/pages'

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <Login />,
  },
  {
    path: '/',
    element: (
      <ProtectedRoute>
        <AppShell />
      </ProtectedRoute>
    ),
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
      { path: 'approvals', element: <Approvals /> },
      { path: 'activity', element: <ActivityLog /> },
      { path: 'settings', element: <Settings /> },
      {
        path: 'users',
        element: (
          <ProtectedRoute requiredRole="admin">
            <Users />
          </ProtectedRoute>
        ),
      },
      { path: '*', element: <NotFound /> },
    ],
  },
])
