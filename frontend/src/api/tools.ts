import client from './client'

export interface ToolParameter {
  name: string
  type: string
  required: boolean
}

export interface ToolInfo {
  name: string
  description: string
  parameters: ToolParameter[]
}

export interface ToolExecuteResult {
  tool_name: string
  success: boolean
  status: string
  data: unknown
  error?: string
  execution_time_ms?: number
}

export const toolsApi = {
  list: () => client.get<ToolInfo[]>('/tools/list'),

  execute: (tool_name: string, params: Record<string, unknown>) =>
    client.post<ToolExecuteResult>('/tools/execute', { tool_name, params }),

  search: (query: string, source = 'both', top_k = 5) =>
    client.post<unknown>('/tools/search', { query, source, top_k }),

  todo: (payload: Record<string, unknown>) =>
    client.post<unknown>('/tools/todo', payload),

  calendar: (payload: Record<string, unknown>) =>
    client.post<unknown>('/tools/calendar', payload),

  email: (payload: Record<string, unknown>) =>
    client.post<unknown>('/tools/email', payload),
}
