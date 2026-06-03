import client from './client'

export interface HealthStatus {
  status: string
  timestamp: string
  version: string
}

export interface HealthData {
  status: string
  version: string
}

export const healthApi = {
  check: () => client.get<HealthData>('/health/'),
  ready: () => client.get<{ ready: boolean }>('/health/ready'),
}
