import client from './client'

export type MemoryType = 'short_term' | 'long_term' | 'episodic'

export interface AgentMemory {
  id: string
  tenant_id?: string | null
  user_id?: string | null
  memory_type: MemoryType
  content: string
  context?: Record<string, unknown>
  importance_score: number
  created_at: string
  expires_at?: string | null
}

export interface MemoryCreatePayload {
  content: string
  memory_type?: MemoryType
  importance_score?: number
  ttl_hours?: number
  session_id?: string
}

export const MEMORY_TYPE_LABELS: Record<MemoryType, string> = {
  short_term: '短期',
  long_term: '长期',
  episodic: '情景',
}

export const memoryApi = {
  list: (params?: { memory_type?: MemoryType; session_id?: string; limit?: number }) =>
    client.get<AgentMemory[]>('/agent/memories', { params }),

  create: (data: MemoryCreatePayload) =>
    client.post<AgentMemory>('/agent/memories', data),

  remove: (id: string) => client.delete<null>(`/agent/memories/${id}`),

  promote: (id: string) =>
    client.post<AgentMemory>(`/agent/memories/${id}/promote`),

  summarizeSession: (session_id: string) =>
    client.post<{ summary: string }>('/agent/memories/summarize', { session_id }),
}
