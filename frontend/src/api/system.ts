import { apiClient } from './client'

export interface DhcpIssue {
  type: string
  count: number
  received: string | null
  expected: string | null
  affected_macs: string[]
}

export interface DhcpRequiredSettings {
  next_server: string
  filename_bios: string
  filename_uefi: string
}

export interface DhcpStatus {
  nodes_connected: number
  nodes_with_issues: number
  last_connection: string | null
  issues: DhcpIssue[]
}

export interface DhcpStatusResponse {
  server_ip: string
  server_port: number
  tftp_enabled: boolean
  tftp_port: number
  required_settings: DhcpRequiredSettings
  status: DhcpStatus
  first_run: boolean
}

export interface ServerInfoResponse {
  version: string
  server_ip: string
  http_port: number
  tftp_enabled: boolean
  tftp_port: number
  dhcp_proxy_enabled: boolean
  dhcp_proxy_port: number
}

export const systemApi = {
  getDhcpStatus(): Promise<DhcpStatusResponse> {
    return apiClient.get<DhcpStatusResponse>('/system/dhcp-status')
  },

  getServerInfo(): Promise<ServerInfoResponse> {
    return apiClient.get<ServerInfoResponse>('/system/info')
  },
}
