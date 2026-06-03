import axios, {
  type AxiosInstance,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from 'axios'
import { ElMessage } from 'element-plus'
import type { APIResponse } from './types'
import { getStoredToken } from './auth'

const axiosClient: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json',
  },
})

axiosClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = getStoredToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error),
)

function formatErrorMessage(data: unknown): string | null {
  if (!data || typeof data !== 'object') return null
  const body = data as Record<string, unknown>
  if (typeof body.message === 'string' && body.message) return body.message
  if (typeof body.detail === 'string' && body.detail) return body.detail
  if (Array.isArray(body.detail)) {
    const labels: Record<string, string> = {
      username: '账号',
      password: '密码',
    }
    return body.detail
      .map((item) => {
        if (!item || typeof item !== 'object') return ''
        const err = item as { loc?: unknown[]; msg?: string; type?: string; ctx?: { min_length?: number } }
        const field = String(err.loc?.[err.loc.length - 1] ?? '')
        const label = labels[field] || field
        if (err.type === 'string_too_short' && err.ctx?.min_length) {
          return `${label}至少 ${err.ctx.min_length} 个字符`
        }
        if (err.type === 'missing') return `${label}为必填项`
        return err.msg ? `${label}: ${err.msg}` : `${label}格式不正确`
      })
      .filter(Boolean)
      .join('；')
  }
  return null
}

axiosClient.interceptors.response.use(
  (response: AxiosResponse) => response.data,
  (error) => {
    const data = error.response?.data
    const message =
      formatErrorMessage(data) ||
      (typeof data === 'string' ? data : null) ||
      error.message ||
      '请求失败'
    if (error.response?.status === 401) {
      const path = window.location.pathname
      if (!path.startsWith('/login')) {
        import('./auth').then(({ clearAuth }) => {
          clearAuth()
          window.location.href = '/login'
        })
      }
    } else {
      ElMessage.error(message)
    }
    return Promise.reject(new Error(message))
  },
)

/** 拦截器已解包为 APIResponse，此处显式标注返回类型 */
const client = {
  get<T>(url: string, config?: Parameters<AxiosInstance['get']>[1]) {
    return axiosClient.get(url, config) as Promise<APIResponse<T>>
  },
  post<T>(url: string, data?: unknown, config?: Parameters<AxiosInstance['post']>[2]) {
    return axiosClient.post(url, data, config) as Promise<APIResponse<T>>
  },
  put<T>(url: string, data?: unknown, config?: Parameters<AxiosInstance['put']>[2]) {
    return axiosClient.put(url, data, config) as Promise<APIResponse<T>>
  },
  delete<T>(url: string, config?: Parameters<AxiosInstance['delete']>[1]) {
    return axiosClient.delete(url, config) as Promise<APIResponse<T>>
  },
}

export default client
