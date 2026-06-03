import client from './client'
import type {
  Knowledge,
  KnowledgeCreate,
  KnowledgeUpdate,
  KnowledgeStats,
  SearchRequest,
  SearchResponse,
} from './types'

export const knowledgeApi = {
  getRecent: (days = 30, limit = 50) =>
    client.get<Knowledge[]>('/knowledge/recent', { params: { days, limit } }),

  getStats: () => client.get<KnowledgeStats>('/knowledge/stats'),

  getById: (id: string) => client.get<Knowledge>(`/knowledge/${id}`),

  create: (data: KnowledgeCreate) => client.post<Knowledge>('/knowledge/create', data),

  update: (id: string, data: KnowledgeUpdate) =>
    client.put<Knowledge>(`/knowledge/${id}`, data),

  delete: (id: string) => client.delete<null>(`/knowledge/${id}`),

  search: (data: SearchRequest) => client.post<SearchResponse>('/knowledge/search', data),
}
