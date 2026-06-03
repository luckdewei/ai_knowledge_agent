import client from './client'
import type { TrendPoint, AttentionShift, KnowledgeNetwork } from './types'

export const insightsApi = {
  getActivityTrend: (days = 90) =>
    client.get<TrendPoint[]>('/insights/trends/activity', { params: { days } }),

  getAttentionShift: (days = 90) =>
    client.get<AttentionShift>('/insights/trends/attention', { params: { days } }),

  getKnowledgeNetwork: (knowledgeId: string, depth = 2) =>
    client.get<KnowledgeNetwork>(`/insights/network/${knowledgeId}`, {
      params: { depth },
    }),

  getReminders: () => client.get<unknown[]>('/insights/reminders'),
}
