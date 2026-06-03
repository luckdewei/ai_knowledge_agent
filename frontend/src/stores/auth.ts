import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  authApi,
  clearAuth,
  getStoredAuth,
  saveAuth,
  type AuthResponse,
  type LoginPayload,
  type RegisterPayload,
  type TenantInfo,
  type UserInfo,
} from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(null)
  const user = ref<UserInfo | null>(null)
  const tenant = ref<TenantInfo | null>(null)

  const isLoggedIn = computed(() => !!token.value)

  function hydrate() {
    const stored = getStoredAuth()
    if (stored) {
      token.value = stored.token
      user.value = stored.user
      tenant.value = stored.tenant
    }
  }

  function applyAuth(data: AuthResponse) {
    saveAuth(data)
    token.value = data.access_token
    user.value = data.user
    tenant.value = data.tenant
  }

  async function login(payload: LoginPayload) {
    const res = await authApi.login(payload)
    if (res.data) applyAuth(res.data)
    return res
  }

  async function register(payload: RegisterPayload) {
    const res = await authApi.register(payload)
    if (res.data) applyAuth(res.data)
    return res
  }

  async function fetchMe() {
    const res = await authApi.me()
    if (res.data) {
      user.value = res.data.user
      tenant.value = res.data.tenant
      localStorage.setItem('pka_auth_user', JSON.stringify(res.data.user))
      localStorage.setItem('pka_auth_tenant', JSON.stringify(res.data.tenant))
    }
    return res
  }

  function logout() {
    clearAuth()
    token.value = null
    user.value = null
    tenant.value = null
  }

  hydrate()

  return {
    token,
    user,
    tenant,
    isLoggedIn,
    login,
    register,
    fetchMe,
    logout,
    hydrate,
  }
})
