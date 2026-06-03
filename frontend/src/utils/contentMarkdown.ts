/** 将杂乱纯文本整理为 Markdown（与后端 markdown_format 逻辑对齐，用于展示与编辑） */

const HEADING_MAX = 80
const BULLET_RE = /^[-*•●]\s+/
const ORDERED_RE = /^(\d+)[.)]\s+/
const NOISE_LINE_RE =
  /^(分享到|扫一扫|登录|注册|首页|相关阅读|推荐阅读|责任编辑|版权所有|Copyright|点赞|收藏|转发|评论)/

function cleanMarkdown(md: string): string {
  return md
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

export function isLikelyMarkdown(text: string): boolean {
  if (/^#{1,6}\s+\S/m.test(text)) return true
  if (text.includes('```')) return true
  if (/\[[^\]]+\]\(https?:\/\//.test(text)) return true
  if (/^\s*[-*+]\s+\S/m.test(text) && (text.match(/\n- /g)?.length ?? 0) >= 2) return true
  if (/^\|.+\|/m.test(text) && text.includes('|---')) return true
  const paras = text.split('\n\n').filter((p) => p.trim().length > 40)
  if (paras.length >= 2 && !/^#{1,6}\s/m.test(text)) return true
  return false
}

function isNoiseLine(line: string): boolean {
  const s = line.trim()
  if (s.startsWith('```') || /^#{1,6}\s/.test(s)) return false
  if (s === '---' || (s.startsWith('|') && s.includes('|', 1))) return false
  if (!s || s.length <= 2) return true
  if (NOISE_LINE_RE.test(s)) return true
  if (/^[-=_*#|·\s]{3,}$/.test(s)) return true
  return s.length < 12 && !/[\u4e00-\u9fffA-Za-z]{4}/.test(s)
}

function mostlyCjk(text: string): boolean {
  let cjk = 0
  let alpha = 0
  for (const c of text) {
    if (c >= '\u4e00' && c <= '\u9fff') cjk++
    else if (/[a-zA-Z]/.test(c)) alpha++
  }
  return cjk > alpha
}

function looksLikeHeading(line: string): boolean {
  if (line.length > HEADING_MAX) return false
  if (/[.。!?！？；;…]$/.test(line)) return false
  if ((line.match(/，/g)?.length ?? 0) > 2 || (line.match(/,/g)?.length ?? 0) > 3) return false
  if (line.length > 40 && (line.includes('，') || line.includes(','))) return false
  return true
}

/** 杂乱纯文本 → Markdown */
export function plainTextToMarkdown(text: string): string {
  if (!text?.trim()) return ''

  let raw = text
  if (raw.includes('<') && raw.includes('>')) {
    raw = raw.replace(/<[^>]+>/g, '\n')
  }

  raw = cleanMarkdown(raw)
  if (isLikelyMarkdown(raw)) return raw

  const lines = raw.split('\n').map((l) => l.trim()).filter((l) => l && !isNoiseLine(l))
  const blocks: string[] = []
  const buf: string[] = []

  const flushBuf = () => {
    if (!buf.length) return
    if (buf.length === 1 && looksLikeHeading(buf[0]!)) {
      blocks.push(`## ${buf[0]}`)
    } else {
      const joined = mostlyCjk(buf.join('')) ? buf.join('') : buf.join(' ')
      blocks.push(joined)
    }
    blocks.push('')
    buf.length = 0
  }

  for (const line of lines) {
    const s = line.trim()
    if (!s) {
      flushBuf()
      continue
    }
    if (BULLET_RE.test(s)) {
      flushBuf()
      blocks.push(s.replace(BULLET_RE, '- '))
      continue
    }
    const om = s.match(ORDERED_RE)
    if (om) {
      flushBuf()
      blocks.push(`${om[1]}. ${s.slice(om[0].length).trim()}`)
      continue
    }
    if (!buf.length && looksLikeHeading(s)) {
      flushBuf()
      blocks.push(`## ${s}`)
      blocks.push('')
      continue
    }
    buf.push(s)
  }
  flushBuf()
  return cleanMarkdown(blocks.join('\n'))
}

function dedupeParagraphs(md: string): string {
  const seen = new Set<string>()
  const kept: string[] = []
  for (const part of md.trim().split(/\n{2,}/)) {
    const key = part.trim().replace(/\s+/g, ' ').slice(0, 400)
    if (!key || seen.has(key)) continue
    seen.add(key)
    kept.push(part.trim())
  }
  return kept.join('\n\n')
}

function polishMarkdown(md: string): string {
  const lines: string[] = []
  let prev: string | null = null
  for (const raw of md.split('\n')) {
    const s = raw.trim()
    if (!s) {
      if (lines.length && lines[lines.length - 1] !== '') lines.push('')
      prev = null
      continue
    }
    if (isNoiseLine(s) || s === prev) continue
    lines.push(raw.trimEnd())
    prev = s
  }
  return dedupeParagraphs(cleanMarkdown(lines.join('\n')))
}

/** 知识正文：已是 Markdown 则轻量清理，否则整理 */
export function formatKnowledgeContent(content: string): string {
  if (!content?.trim()) return ''
  if (isLikelyMarkdown(content)) return polishMarkdown(content)
  return plainTextToMarkdown(content)
}
