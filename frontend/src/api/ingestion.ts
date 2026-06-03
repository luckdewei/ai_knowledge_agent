import client from './client'
import type { IngestResponse } from './types'

export const ingestionApi = {
  uploadFile: (
    file: File,
    options?: { auto_tag?: boolean; auto_summarize?: boolean },
  ) => {
    const form = new FormData()
    form.append('file', file)
    form.append('auto_tag', String(options?.auto_tag ?? true))
    form.append('auto_summarize', String(options?.auto_summarize ?? false))
    return client.post<IngestResponse>('/ingestion/file', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  /** 抓取并解析网页正文后写入知识库 */
  ingestUrl: (
    url: string,
    options?: {
      auto_tag?: boolean
      auto_summarize?: boolean
      fetch_metadata?: boolean
    },
  ) =>
    client.post<IngestResponse>('/ingestion/url', {
      url,
      auto_tag: options?.auto_tag ?? true,
      auto_summarize: options?.auto_summarize ?? false,
      fetch_metadata: options?.fetch_metadata ?? true,
    }),
}
