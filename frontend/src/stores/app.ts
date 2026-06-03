import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAppStore = defineStore('app', () => {
  const globalLoading = ref(false)
  const sidebarCollapsed = ref(false)

  function setLoading(v: boolean) {
    globalLoading.value = v
  }

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  return { globalLoading, sidebarCollapsed, setLoading, toggleSidebar }
})
