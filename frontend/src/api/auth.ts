import client from './client'

/** 内部数据空间 ID，用于会话隔离 */
export interface TenantInfo {
  id: string
  name?: string
  slug?: string
}

export interface UserInfo {
  id: string
  username: string
  display_name?: string | null
}

export interface LoginPayload {
  username: string
  password: string
}

export interface RegisterPayload {
  username: string
  password: string
}

export interface AuthResponse {
  access_token: string
  token_type: string
  user: UserInfo
  tenant: TenantInfo
}

const TOKEN_KEY = 'pka_access_token'
const AUTH_USER_KEY = 'pka_auth_user'
const AUTH_TENANT_KEY = 'pka_auth_tenant'

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function getStoredAuth(): {
  token: string
  user: UserInfo
  tenant: TenantInfo
} | null {
  const token = getStoredToken()
  const userRaw = localStorage.getItem(AUTH_USER_KEY)
  const tenantRaw = localStorage.getItem(AUTH_TENANT_KEY)
  if (!token || !userRaw || !tenantRaw) return null
  try {
    return {
      token,
      user: JSON.parse(userRaw) as UserInfo,
      tenant: JSON.parse(tenantRaw) as TenantInfo,
    }
  } catch {
    return null
  }
}

export function saveAuth(data: AuthResponse) {
  localStorage.setItem(TOKEN_KEY, data.access_token)
  localStorage.setItem(AUTH_USER_KEY, JSON.stringify(data.user))
  localStorage.setItem(AUTH_TENANT_KEY, JSON.stringify(data.tenant))
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(AUTH_USER_KEY)
  localStorage.removeItem(AUTH_TENANT_KEY)
  localStorage.removeItem('pka_chat_session')
}

export const authApi = {
  login: (data: LoginPayload) =>
    client.post<AuthResponse>('/auth/login', data),

  register: (data: RegisterPayload) =>
    client.post<AuthResponse>('/auth/register', data),

  me: () =>
    client.get<{ user: UserInfo; tenant: TenantInfo }>('/auth/me'),
}
