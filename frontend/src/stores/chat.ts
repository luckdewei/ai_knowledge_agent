import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import { agentApi, streamChat, type ChatSession, type SessionMessage } from '@/api/agent'
import type { ChatMessage, SaveSuggestion } from '@/api/types'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

function uid() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

function sessionStorageKey() {
  const auth = useAuthStore()
  return auth.tenant?.id ? `pka_chat_session_${auth.tenant.id}` : 'pka_chat_session'
}

function pushThinkingStep(msg: ChatMessage, step: string) {
  const text = step.trim()
  if (!text) return
  if (!msg.thinkingSteps) msg.thinkingSteps = []
  const last = msg.thinkingSteps[msg.thinkingSteps.length - 1]
  if (last !== text) {
    msg.thinkingSteps.push(text)
  }
  msg.thinking = text
}

function mapSessionMessage(m: SessionMessage): ChatMessage {
  return {
    id: m.id,
    role: m.role as ChatMessage['role'],
    content: m.content,
    thinking: m.thinking ?? undefined,
    thinkingSteps: m.thinking ? [m.thinking] : undefined,
  }
}

export const useChatStore = defineStore('chat', () => {
  const sessionId = ref('')
  const sessions = ref<ChatSession[]>([])
  const messages = ref<ChatMessage[]>([])
  const streaming = ref(false)
  const useStream = ref(true)
  const useMemory = ref(true)
  const sessionsLoading = ref(false)
  let abortController: AbortController | null = null
  let initialized = false

  function addMessage(
    role: ChatMessage['role'],
    content: string,
    extra?: Partial<ChatMessage>,
  ) {
    const msg = reactive({
      id: uid(),
      role,
      content,
      ...extra,
    }) as ChatMessage
    messages.value.push(msg)
    return msg
  }

  async function fetchSessions() {
    sessionsLoading.value = true
    try {
      const res = await agentApi.listSessions()
      sessions.value = res.data ?? []
    } catch (e) {
      ElMessage.error(`加载历史对话失败：${(e as Error).message}`)
    } finally {
      sessionsLoading.value = false
    }
  }

  async function loadMessages(id: string) {
    try {
      const res = await agentApi.listMessages(id)
      messages.value = (res.data ?? []).map(mapSessionMessage)
    } catch (e) {
      messages.value = []
      ElMessage.error(`加载消息失败：${(e as Error).message}`)
    }
  }

  async function selectSession(id: string) {
    if (streaming.value || sessionId.value === id) return
    stop()
    sessionId.value = id
    localStorage.setItem(sessionStorageKey(), id)
    await loadMessages(id)
  }

  async function newChat() {
    if (streaming.value) return
    stop()
    try {
      const res = await agentApi.createSession()
      const id = res.data?.id
      if (!id) throw new Error('未返回会话 ID')
      sessionId.value = id
      messages.value = []
      localStorage.setItem(sessionStorageKey(), id)
      await fetchSessions()
    } catch (e) {
      ElMessage.error(`创建对话失败：${(e as Error).message}`)
    }
  }

  async function deleteSession(id: string) {
    try {
      await agentApi.deleteSession(id)
      sessions.value = sessions.value.filter((s) => s.id !== id)
      if (sessionId.value === id) {
        sessionId.value = ''
        messages.value = []
        localStorage.removeItem(sessionStorageKey())
        if (sessions.value.length) {
          await selectSession(sessions.value[0].id)
        }
      }
      ElMessage.success('已删除对话')
    } catch (e) {
      ElMessage.error(`删除失败：${(e as Error).message}`)
    }
  }

  async function ensureSessionForSend(): Promise<string> {
    if (sessionId.value && sessionId.value !== 'default') {
      const exists = sessions.value.some((s) => s.id === sessionId.value)
      if (exists) return sessionId.value
    }
    const res = await agentApi.createSession()
    const id = res.data?.id
    if (!id) throw new Error('无法创建会话')
    sessionId.value = id
    localStorage.setItem(sessionStorageKey(), id)
    return id
  }

  async function send(query: string) {
    if (!query.trim() || streaming.value) return

    try {
      await ensureSessionForSend()
    } catch (e) {
      ElMessage.error((e as Error).message)
      return
    }

    addMessage('user', query.trim())
    streaming.value = true

    if (useStream.value) {
      const assistant = addMessage('assistant', '', { streaming: true })
      abortController = new AbortController()

      try {
        await streamChat(
          query,
          sessionId.value,
          (event) => {
            if (event.type === 'session' && event.content) {
              assistant.sessionId = event.content
              sessionId.value = event.content
              localStorage.setItem(sessionStorageKey(), event.content)
            }
            if (
              (event.type === 'thinking_start' ||
                event.type === 'thinking_step' ||
                event.type === 'status') &&
              event.content
            ) {
              pushThinkingStep(assistant, event.content)
            }
            if (event.type === 'tool_call' && event.content) {
              try {
                const log = JSON.parse(event.content) as {
                  tool?: string
                  success?: boolean
                  error?: string
                }
                if (!assistant.toolCalls) assistant.toolCalls = []
                assistant.toolCalls.push({
                  tool: log.tool ?? 'unknown',
                  success: !!log.success,
                  error: log.error,
                })
              } catch {
                /* ignore */
              }
            }
            if (event.type === 'memory_context' && event.content) {
              try {
                assistant.memoriesUsed = JSON.parse(
                  event.content,
                ) as ChatMessage['memoriesUsed']
              } catch {
                /* ignore */
              }
            }
            if (event.type === 'memory_saved' && event.content) {
              try {
                const saved = JSON.parse(event.content) as Array<{
                  content: string
                  memory_type?: string
                }>
                assistant.memoriesUsed = saved.map((s, i) => ({
                  id: String(i),
                  content: s.content,
                  memory_type: s.memory_type,
                }))
              } catch {
                /* ignore */
              }
            }
            if (event.type === 'save_suggestion' && event.content) {
              try {
                assistant.saveSuggestion = JSON.parse(
                  event.content,
                ) as SaveSuggestion
              } catch {
                /* ignore */
              }
            }
            if (event.type === 'content' && event.content) {
              assistant.content += event.content
            }
            if (event.type === 'error' && event.content) {
              assistant.thinking = ''
              assistant.content =
                assistant.content || `错误：${event.content}`
            }
            if (event.type === 'end') {
              assistant.streaming = false
              if (assistant.thinkingSteps?.length) {
                pushThinkingStep(assistant, '✓ 处理完成')
              }
            }
          },
          abortController.signal,
          { use_memory: useMemory.value, auto_memory: useMemory.value },
        )
        assistant.streaming = false
        if (!assistant.content && !assistant.thinking) {
          assistant.content = '（未收到回复内容）'
        }
      } catch (e) {
        if ((e as Error).name !== 'AbortError') {
          assistant.thinking = ''
          assistant.content =
            assistant.content || `错误：${(e as Error).message}`
        }
        assistant.streaming = false
      }
    } else {
      try {
        const res = await agentApi.chat({
          query,
          session_id: sessionId.value,
          use_memory: useMemory.value,
          auto_memory: useMemory.value,
        })
        addMessage('assistant', res.data?.response ?? '（无响应）')
      } catch (e) {
        addMessage('assistant', `错误：${(e as Error).message}`)
      }
    }

    streaming.value = false
    abortController = null
    await fetchSessions()
  }

  function stop() {
    abortController?.abort()
    streaming.value = false
    const last = messages.value[messages.value.length - 1]
    if (last?.role === 'assistant') {
      last.streaming = false
    }
  }

  async function init() {
    if (initialized) return
    initialized = true
    await fetchSessions()
    const stored = localStorage.getItem(sessionStorageKey())
    if (stored && stored !== 'default') {
      const found = sessions.value.some((s) => s.id === stored)
      if (found) {
        sessionId.value = stored
        await loadMessages(stored)
        return
      }
    }
    if (sessions.value.length) {
      await selectSession(sessions.value[0].id)
    }
  }

  function reset() {
    stop()
    sessionId.value = ''
    sessions.value = []
    messages.value = []
    initialized = false
    localStorage.removeItem(sessionStorageKey())
  }

  async function saveSuggestionToKnowledge(messageId: string) {
    const msg = messages.value.find((m) => m.id === messageId)
    if (!msg?.saveSuggestion || msg.savedKnowledgeId || msg.saving) return

    msg.saving = true
    try {
      const res = await agentApi.saveKnowledge({
        title: msg.saveSuggestion.title,
        content: msg.saveSuggestion.content,
        tags: msg.saveSuggestion.tags,
        source_query: msg.saveSuggestion.source_query,
      })
      msg.savedKnowledgeId = res.data?.knowledge_id
      ElMessage.success(`已保存到知识库：${res.data?.title ?? ''}`)
    } catch (e) {
      ElMessage.error(`保存失败：${(e as Error).message}`)
    } finally {
      msg.saving = false
    }
  }

  return {
    sessionId,
    sessions,
    messages,
    streaming,
    useStream,
    useMemory,
    sessionsLoading,
    init,
    fetchSessions,
    newChat,
    selectSession,
    deleteSession,
    send,
    stop,
    reset,
    saveSuggestionToKnowledge,
  }
})
