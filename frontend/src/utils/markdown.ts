import { marked } from 'marked'
import DOMPurify from 'dompurify'

marked.setOptions({
  breaks: true,
  gfm: true,
})

/** 将 Markdown 转为可安全插入的 HTML */
export function renderMarkdown(content: string): string {
  if (!content?.trim()) return ''
  const raw = marked.parse(content, { async: false }) as string
  return DOMPurify.sanitize(raw, {
    ADD_ATTR: ['target', 'rel'],
  })
}
