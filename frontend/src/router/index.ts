import { createRouter, createWebHistory } from 'vue-router'
import { getStoredToken } from '@/api/auth'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { title: '登录', public: true },
  },
  {
    path: '/',
    name: 'Dashboard',
    component: () => import('@/views/Dashboard.vue'),
    meta: { title: '洞察看板' },
  },
  {
    path: '/knowledge',
    name: 'KnowledgeBase',
    component: () => import('@/views/KnowledgeBase.vue'),
    meta: { title: '知识库' },
  },
  {
    path: '/agent',
    name: 'AgentChat',
    component: () => import('@/views/AgentChat.vue'),
    meta: { title: 'Agent 对话' },
  },
  {
    path: '/tools',
    name: 'ToolsConsole',
    component: () => import('@/views/ToolsConsole.vue'),
    meta: { title: '工具调用' },
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('@/views/Settings.vue'),
    meta: { title: '系统设置' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const isPublic = to.meta.public === true
  const token = getStoredToken()
  if (!isPublic && !token) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (to.path === '/login' && token) {
    return { path: '/' }
  }
})

router.afterEach((to) => {
  const title = (to.meta.title as string) || '知识助手'
  document.title = `${title} - 智能个人知识库`
})

export default router
