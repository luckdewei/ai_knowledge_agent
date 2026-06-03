/** 统一 API 响应 */
export interface APIResponse<T = unknown> {
  success: boolean
  code: number
  message: string
  data: T
  timestamp: string
}

export type SourceType =
  | 'file'
  | 'url'
  | 'clipboard'
  | 'voice'
  | 'wechat'
  | 'agent'

export interface Knowledge {
  id: string
  title: string
  content: string
  source_type: SourceType
  source_uri?: string | null
  tags?: string[] | null
  metadata?: Record<string, unknown> | null
  content_hash?: string | null
  created_at: string
  updated_at: string
  last_accessed_at?: string | null
}

export interface KnowledgeCreate {
  title: string
  content: string
  source_type: SourceType
  source_uri?: string
  tags?: string[]
}

export interface KnowledgeUpdate {
  title?: string
  content?: string
  tags?: string[]
}

export interface SearchRequest {
  query: string
  top_k?: number
  source_type?: string
  tags?: string[]
  min_similarity?: number
}

export interface SearchResult {
  knowledge: Knowledge
  similarity_score: number
}

export interface SearchResponse {
  results: SearchResult[]
  total: number
  query_time_ms: number
}

export interface KnowledgeStats {
  total_knowledge: number
  by_source_type: Record<string, number>
  top_tags: { tag: string; count: number }[]
}

export interface TrendPoint {
  date: string
  count: number
  tags: string[]
  top_keywords: string[]
}

export interface AttentionShift {
  period: { early: string; late: string }
  rising_tags: TagChange[]
  falling_tags: TagChange[]
  insights?: string[]
}

export interface TagChange {
  tag: string
  early_count: number
  late_count: number
  change_percent: number
  trend: 'up' | 'down' | 'stable'
}

export interface GraphNode {
  id: string
  title: string
  type: string
}

export interface GraphEdge {
  source: string
  target: string
  type: string
  weight: number
}

export interface KnowledgeNetwork {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface ToolCallLog {
  tool: string
  success: boolean
  error?: string
}

export interface SaveSuggestion {
  title: string
  content: string
  tags?: string[]
  source_query?: string
}

export interface MemorySnippet {
  id?: string
  memory_type?: string
  content: string
  importance?: number
  created_at?: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  sessionId?: string
  streaming?: boolean
  /** 当前进行中的步骤（兼容） */
  thinking?: string
  /** 完整思考过程（逐步追加，生成回答后仍保留） */
  thinkingSteps?: string[]
  toolCalls?: ToolCallLog[]
  /** 本轮回答参考的记忆 */
  memoriesUsed?: MemorySnippet[]
  saveSuggestion?: SaveSuggestion
  savedKnowledgeId?: string
  saving?: boolean
}

export type StreamEventType =
  | 'session'
  | 'thinking_start'
  | 'thinking_step'
  | 'status'
  | 'tool_call'
  | 'memory_context'
  | 'memory_saved'
  | 'save_suggestion'
  | 'content'
  | 'error'
  | 'end'

export interface StreamEvent {
  type: StreamEventType
  content?: string
}

export interface IngestResponse {
  success?: boolean
  knowledge_id?: string
  title?: string
  content_preview?: string
  message?: string
  auto_tags?: string[]
  auto_summary?: string
  is_duplicate?: boolean
  is_updated?: boolean
  error?: string
  processing_time_ms?: number
}
