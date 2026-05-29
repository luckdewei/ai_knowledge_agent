import { createRouter, createWebHistory } from 'vue-router'
// import Dashboard from '@/views/Dashboard.vue'
// import KnowledgeBase from '@/views/KnowledgeBase.vue'
// import AgentChat from '@/views/AgentChat.vue'

const routes = [
  {
    path: '/',
    name: 'Dashboard',
    component: () => import('@/views/Dashboard.vue'),
  },
  //   { path: '/knowledge', name: 'KnowledgeBase', component: KnowledgeBase },
  //   { path: '/agent', name: 'AgentChat', component: AgentChat },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
