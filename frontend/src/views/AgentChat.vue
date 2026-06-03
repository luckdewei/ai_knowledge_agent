<template>
  <div class="agent-layout">
    <aside class="session-sidebar">
      <el-button type="primary" class="new-chat-btn" @click="chatStore.newChat">
        <el-icon><Plus /></el-icon>
        新对话
      </el-button>

      <el-scrollbar class="session-list">
        <el-skeleton v-if="chatStore.sessionsLoading" :rows="6" animated />
        <el-empty
          v-else-if="!chatStore.sessions.length"
          description="暂无历史对话"
          :image-size="64"
        />
        <div
          v-for="s in chatStore.sessions"
          :key="s.id"
          class="session-item"
          :class="{ active: s.id === chatStore.sessionId }"
          @click="chatStore.selectSession(s.id)"
        >
          <div class="session-title">{{ sessionTitle(s) }}</div>
          <div class="session-meta">{{ formatTime(s.updated_at) }}</div>
          <el-button
            class="session-delete"
            text
            type="danger"
            size="small"
            @click.stop="onDeleteSession(s.id)"
          >
            删除
          </el-button>
        </div>
      </el-scrollbar>
    </aside>

    <div class="chat-main">
      <el-card shadow="never" class="chat-card">
        <template #header>
          <div class="chat-header">
            <span>Agent 对话</span>
            <div class="header-actions">
              <el-switch
                v-model="chatStore.useMemory"
                active-text="智能记忆"
                inactive-text="智能记忆"
                :disabled="chatStore.streaming"
              />
              <el-switch
                v-model="chatStore.useStream"
                active-text="流式"
                inactive-text="普通"
                :disabled="chatStore.streaming"
              />
            </div>
          </div>
        </template>

        <el-scrollbar ref="scrollRef" class="messages-area" height="calc(100vh - 220px)">
          <div v-if="!chatStore.messages.length" class="welcome">
            <el-icon :size="48" color="#1890ff"><ChatDotRound /></el-icon>
            <h3>个人知识库助手</h3>
            <p>点击「新对话」开始；记忆由 AI 自动判断是否保存，无需手动操作。</p>
            <div class="suggestions">
              <el-tag
                v-for="s in suggestions"
                :key="s"
                class="suggestion-tag"
                @click="input = s"
              >
                {{ s }}
              </el-tag>
            </div>
          </div>

          <div
            v-for="msg in chatStore.messages"
            :key="msg.id"
            class="message"
            :class="msg.role"
          >
            <div class="avatar">
              <el-avatar :size="36" :style="avatarStyle(msg.role)">
                {{ msg.role === 'user' ? '我' : 'AI' }}
              </el-avatar>
            </div>
            <div class="bubble">
              <div
                v-if="msg.thinkingSteps?.length || msg.thinking"
                class="thinking-chain"
              >
                <div class="thinking-title">思考过程</div>
                <div
                  v-for="(step, idx) in msg.thinkingSteps?.length
                    ? msg.thinkingSteps
                    : [msg.thinking]"
                  :key="idx"
                  class="thinking-line"
                >
                  <el-icon
                    v-if="msg.streaming && idx === (msg.thinkingSteps?.length ?? 1) - 1"
                    class="is-loading"
                  >
                    <Loading />
                  </el-icon>
                  <span v-else class="step-done">✓</span>
                  <span>{{ step }}</span>
                </div>
              </div>
              <div v-if="msg.memoriesUsed?.length" class="memory-used">
                <div class="memory-used-title">记忆</div>
                <div
                  v-for="(m, i) in msg.memoriesUsed"
                  :key="m.id ?? i"
                  class="memory-used-item"
                >
                  <span>{{ m.content }}</span>
                </div>
              </div>
              <div v-if="msg.toolCalls?.length" class="tool-calls">
                <el-tag
                  v-for="(tc, i) in msg.toolCalls"
                  :key="i"
                  size="small"
                  :type="tc.success ? 'success' : 'danger'"
                >
                  {{ tc.tool }}{{ tc.success ? ' ✓' : ' ✗' }}
                </el-tag>
              </div>
              <div class="content">
                <MarkdownBody
                  v-if="msg.role === 'assistant' && msg.content"
                  :content="msg.content"
                />
                <span v-else-if="msg.role === 'user'" class="user-text">{{
                  msg.content
                }}</span>
                <span v-else-if="!msg.content && msg.streaming" class="muted"
                  >思考中…</span
                >
                <span v-if="msg.streaming" class="cursor">▋</span>
              </div>
              <div
                v-if="msg.saveSuggestion && !msg.savedKnowledgeId"
                class="save-actions"
              >
                <el-button
                  type="primary"
                  size="small"
                  plain
                  :loading="msg.saving"
                  :disabled="msg.streaming"
                  @click="chatStore.saveSuggestionToKnowledge(msg.id)"
                >
                  保存到知识库
                </el-button>
              </div>
              <el-tag
                v-if="msg.savedKnowledgeId"
                size="small"
                type="success"
                class="saved-tag"
              >
                已入库
              </el-tag>
            </div>
          </div>
        </el-scrollbar>

        <div class="input-area">
          <el-input
            v-model="input"
            type="textarea"
            :rows="3"
            placeholder="输入问题，Enter 发送；首轮会自动创建对话"
            :disabled="chatStore.streaming"
            @keydown.enter.exact.prevent="send"
          />
          <div class="input-actions">
            <el-button
              v-if="chatStore.streaming"
              type="danger"
              @click="chatStore.stop"
            >
              停止
            </el-button>
            <el-button
              v-else
              type="primary"
              :disabled="!input.trim()"
              @click="send"
            >
              发送
            </el-button>
          </div>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, onMounted } from 'vue'
import MarkdownBody from '@/components/MarkdownBody.vue'
import { useChatStore } from '@/stores/chat'
import type { ChatMessage } from '@/api/types'
import type { ChatSession } from '@/api/agent'
import { ElMessageBox } from 'element-plus'

const chatStore = useChatStore()
const input = ref('')
const scrollRef = ref<{ setScrollTop: (n: number) => void } | null>(null)

const suggestions = [
  '我叫小明，主要用 Python 做数据分析',
  '最近一周我学了什么？',
  '帮我总结 Python 相关笔记',
]

onMounted(() => {
  chatStore.init()
})

function avatarStyle(role: ChatMessage['role']) {
  return role === 'user'
    ? { background: '#1890ff' }
    : { background: '#52c41a' }
}

function sessionTitle(s: ChatSession) {
  return (s.title || '').trim() || '新对话'
}

function formatTime(iso: string | null) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  if (sameDay) {
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

async function onDeleteSession(id: string) {
  try {
    await ElMessageBox.confirm('确定删除该对话？消息将无法恢复。', '删除对话', {
      type: 'warning',
    })
    await chatStore.deleteSession(id)
  } catch {
    /* cancel */
  }
}

async function send() {
  const q = input.value.trim()
  if (!q) return
  input.value = ''
  await chatStore.send(q)
  await nextTick()
  scrollRef.value?.setScrollTop(99999)
}

function scrollToBottom() {
  nextTick(() => scrollRef.value?.setScrollTop(99999))
}

watch(() => chatStore.messages.length, scrollToBottom)
watch(
  () =>
    chatStore.messages
      .map((m) => `${m.content.length}:${m.streaming}`)
      .join('|'),
  scrollToBottom,
)
</script>

<style scoped>
.agent-layout {
  display: flex;
  gap: 0;
  height: calc(100vh - 120px);
  min-height: 520px;
  margin: -8px -12px 0;
}

.session-sidebar {
  width: 260px;
  flex-shrink: 0;
  background: #fafafa;
  border-right: 1px solid #e8e8e8;
  display: flex;
  flex-direction: column;
  padding: 12px;
}

.new-chat-btn {
  width: 100%;
  margin-bottom: 12px;
}

.session-list {
  flex: 1;
  min-height: 0;
}

.session-item {
  position: relative;
  padding: 10px 12px;
  margin-bottom: 6px;
  border-radius: 8px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: background 0.15s;
}

.session-item:hover {
  background: #f0f0f0;
}

.session-item.active {
  background: #e6f4ff;
  border-color: #91caff;
}

.session-title {
  font-size: 14px;
  color: #333;
  line-height: 1.4;
  padding-right: 40px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-meta {
  font-size: 11px;
  color: #999;
  margin-top: 4px;
}

.session-delete {
  position: absolute;
  right: 4px;
  top: 8px;
  opacity: 0;
}

.session-item:hover .session-delete {
  opacity: 1;
}

.chat-main {
  flex: 1;
  min-width: 0;
  padding: 0 12px 12px;
}

.chat-card {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.welcome {
  text-align: center;
  padding: 48px 24px;
  color: #666;
}

.welcome h3 {
  margin: 16px 0 8px;
  color: #333;
}

.suggestions {
  margin-top: 24px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
}

.suggestion-tag {
  cursor: pointer;
}

.message {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  padding: 0 8px;
}

.message.user {
  flex-direction: row-reverse;
}

.message.user .bubble {
  background: #1890ff;
  color: #fff;
}

.message.user .memory-used,
.message.user .thinking-chain {
  color: rgba(255, 255, 255, 0.92);
}

.message.assistant .bubble {
  background: #f5f5f5;
  color: #333;
}

.bubble {
  max-width: 78%;
  padding: 12px 16px;
  border-radius: 12px;
  line-height: 1.6;
  word-break: break-word;
}

.content .user-text {
  white-space: pre-wrap;
}

.content .muted {
  color: #999;
  font-size: 13px;
}

.thinking-chain {
  font-size: 12px;
  color: #666;
  margin-bottom: 10px;
  padding: 8px 10px;
  background: rgba(0, 0, 0, 0.04);
  border-radius: 8px;
  border-left: 3px solid #1890ff;
}

.thinking-title {
  font-weight: 600;
  margin-bottom: 6px;
}

.thinking-line {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-bottom: 4px;
}

.step-done {
  color: #52c41a;
  flex-shrink: 0;
}

.memory-used {
  font-size: 12px;
  margin-bottom: 8px;
  padding: 6px 8px;
  background: rgba(24, 144, 255, 0.08);
  border-radius: 6px;
}

.memory-used-title {
  font-weight: 600;
  margin-bottom: 4px;
}

.memory-used-item {
  margin-bottom: 2px;
  line-height: 1.45;
}

.tool-calls {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.save-actions {
  margin-top: 8px;
}

.saved-tag {
  margin-top: 8px;
}

.cursor {
  animation: blink 1s step-end infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

.input-area {
  margin-top: 12px;
}

.input-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}
</style>
