import client from './client'

export type SettingsSource = 'env' | 'runtime' | 'none'

export interface ApiKeyFieldView {
  key: string
  env_var: string
  label: string
  description: string
  group: string
  masked_value: string
  source: SettingsSource
  configured: boolean
  env_configured: boolean
  runtime_configured: boolean
}

export interface UpdateApiKeysPayload {
  deepseek_api_key?: string | null
  embedding_api_key?: string | null
  speech_api_key?: string | null
  tavily_api_key?: string | null
  smtp_username?: string | null
  smtp_password?: string | null
}

export const settingsApi = {
  getKeys: () =>
    client.get<{ fields: ApiKeyFieldView[]; hint: string }>('/settings/keys'),

  saveKeys: (data: UpdateApiKeysPayload) =>
    client.put<{ fields: ApiKeyFieldView[]; message: string }>(
      '/settings/keys',
      data,
    ),
}
