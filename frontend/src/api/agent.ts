import client from './client'
import { getStoredToken } from './auth'
import type { StreamEvent } from './types'

export interface ChatRequest {
  query: string
  session_id?: string
  stream?: boolean
  use_memory?: boolean
  auto_memory?: boolean
}

export interface ChatData {
  response: string
  session_id: string
  thinking_chain?: Record<string, unknown> | null
}

export interface ChatSession {
  id: string
  title: string | null
  created_at: string | null
  updated_at: string | null
}

export interface SessionMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  thinking?: string | null
  created_at: string | null
}

export interface SaveKnowledgeFromChatRequest {
  title: string
  content: string
  tags?: string[]
  source_query?: string
}

export const agentApi = {
  chat: (data: ChatRequest) =>
    client.post<ChatData>('/agent/chat', {
      ...data,
      stream: false,
    }),

  createSession: () =>
    client.post<{ id: string; title: string | null }>('/agent/sessions'),

  listSessions: () => client.get<ChatSession[]>('/agent/sessions'),

  listMessages: (sessionId: string) =>
    client.get<SessionMessage[]>(`/agent/sessions/${sessionId}/messages`),

  deleteSession: (sessionId: string) =>
    client.delete<null>(`/agent/sessions/${sessionId}`),

  saveKnowledge: (data: SaveKnowledgeFromChatRequest) =>
    client.post<{ knowledge_id: string; title: string }>(
      '/agent/save-knowledge',
      data,
    ),
}

function parseSseChunk(chunk: string, onEvent: (event: StreamEvent) => void) {
  const lines = chunk.split('\n')
  for (const raw of lines) {
    const line = raw.trim()
    if (!line.startsWith('data:')) continue
    const jsonStr = line.startsWith('data: ') ? line.slice(6) : line.slice(5).trim()
    if (!jsonStr) continue
    try {
      onEvent(JSON.parse(jsonStr) as StreamEvent)
    } catch {
      /* 忽略畸形行 */
    }
  }
}

/** SSE 流式对话 */
export async function streamChat(
  query: string,
  sessionId: string,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
  options?: { use_memory?: boolean; auto_memory?: boolean },
): Promise<void> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'text/event-stream',
  }
  const token = getStoredToken()
  if (token) headers.Authorization = `Bearer ${token}`

  const res = await fetch('/api/agent/chat', {
    method: 'POST',
    headers,
    body: JSON.stringify({
      query,
      session_id: sessionId,
      stream: true,
      use_memory: options?.use_memory ?? true,
      auto_memory: options?.auto_memory ?? true,
    }),
    signal,
  })

  const contentType = res.headers.get('content-type') ?? ''

  if (!res.ok) {
    if (contentType.includes('application/json')) {
      const err = await res.json().catch(() => ({ message: res.statusText }))
      throw new Error(
        (err as { message?: string; detail?: string }).message ||
          (err as { detail?: string }).detail ||
          '流式请求失败',
      )
    }
    const text = await res.text().catch(() => res.statusText)
    throw new Error(text || '流式请求失败')
  }

  if (!contentType.includes('text/event-stream')) {
    const data = await res.json().catch(() => null)
    if (data?.data?.response) {
      onEvent({ type: 'content', content: data.data.response })
      onEvent({ type: 'end' })
      return
    }
    throw new Error('服务器未返回事件流')
  }

  const reader = res.body?.getReader()
  if (!reader) throw new Error('无法读取响应流')

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''

    for (const part of parts) {
      parseSseChunk(part, onEvent)
    }
  }

  if (buffer.trim()) {
    parseSseChunk(buffer, onEvent)
  }
}
