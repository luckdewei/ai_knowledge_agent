import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { knowledgeApi } from '@/api/knowledge'
import type { Knowledge, KnowledgeUpdate, SearchResult } from '@/api/types'

export const useKnowledgeStore = defineStore('knowledge', () => {
  const items = ref<Knowledge[]>([])
  const selectedId = ref<string | null>(null)
  const loading = ref(false)
  const searchResults = ref<SearchResult[]>([])
  const searchQuery = ref('')
  const stats = ref<{ total_knowledge: number; top_tags: { tag: string; count: number }[] } | null>(
    null,
  )

  const selected = computed(() =>
    items.value.find((k) => k.id === selectedId.value) ?? null,
  )

  async function fetchRecent(days = 90, limit = 100) {
    loading.value = true
    try {
      const res = await knowledgeApi.getRecent(days, limit)
      items.value = res.data ?? []
      if (!selectedId.value && items.value.length) {
        selectedId.value = items.value[0].id
      }
    } finally {
      loading.value = false
    }
  }

  async function fetchStats() {
    const res = await knowledgeApi.getStats()
    stats.value = res.data ?? null
  }

  async function select(id: string) {
    selectedId.value = id
    const exists = items.value.find((k) => k.id === id)
    if (!exists) {
      const res = await knowledgeApi.getById(id)
      if (res.data) items.value.unshift(res.data)
    }
  }

  async function search(query: string) {
    if (!query.trim()) {
      searchResults.value = []
      searchQuery.value = ''
      return fetchRecent()
    }
    searchQuery.value = query
    loading.value = true
    try {
      const res = await knowledgeApi.search({ query, top_k: 20 })
      searchResults.value = res.data?.results ?? []
    } finally {
      loading.value = false
    }
  }

  async function update(id: string, data: KnowledgeUpdate) {
    const res = await knowledgeApi.update(id, data)
    if (res.data) {
      const idx = items.value.findIndex((k) => k.id === id)
      if (idx >= 0) items.value[idx] = res.data
      ElMessage.success('保存成功')
    }
  }

  async function remove(id: string) {
    await knowledgeApi.delete(id)
    items.value = items.value.filter((k) => k.id !== id)
    if (selectedId.value === id) {
      selectedId.value = items.value[0]?.id ?? null
    }
    ElMessage.success('已删除')
  }

  function prepend(item: Knowledge) {
    items.value.unshift(item)
    selectedId.value = item.id
  }

  const displayList = computed(() =>
    searchQuery.value
      ? searchResults.value.map((r) => r.knowledge)
      : items.value,
  )

  return {
    items,
    selectedId,
    selected,
    loading,
    searchResults,
    searchQuery,
    stats,
    displayList,
    fetchRecent,
    fetchStats,
    select,
    search,
    update,
    remove,
    prepend,
  }
})
