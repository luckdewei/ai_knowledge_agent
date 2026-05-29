import client from './client'

export interface HealthStatus {
  status: string
  timestamp: string
  version: string
}

export const healthApi = {
  check: () => client.get<HealthStatus>('/health/'),
  ready: () => client.get<{ ready: boolean }>('/health/ready'),
}
