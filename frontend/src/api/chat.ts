/**
 * 流式聊天 API。
 *
 * 使用 fetch + ReadableStream，而不是 Axios：
 * Axios 对文本流支持较弱，项目里原本就用 fetch。
 *
 * 协议说明（当前并非 SSE）：
 * - 正文：text/plain 增量文本
 * - 响应头 X-Conversation-Title：可选新标题（URL 编码）
 * - 响应头 X-Knowledge-Status：none | hit | empty
 * - 响应头 X-Knowledge-Citations：检索到的参考来源 JSON（URL 编码）
 */

export type StreamChunkHandler = (chunk: string) => void
export type StreamTitleHandler = (title: string) => void
export type StreamCitationsHandler = (
  citations: KnowledgeCitation[],
  status: KnowledgeStatus,
) => void

/** 与后端 chat.py 中 Header 名称保持一致 */
const TITLE_HEADER = 'X-Conversation-Title'
const CITATIONS_HEADER = 'X-Knowledge-Citations'
const KNOWLEDGE_STATUS_HEADER = 'X-Knowledge-Status'

export type KnowledgeStatus = 'none' | 'hit' | 'empty'

/** 来自检索结果的参考来源（非模型编造，非逐句证据对齐） */
export interface KnowledgeCitation {
  filename: string
  page: number | null
  snippet?: string
  distance?: number | null
  chunk_count?: number
}

export interface StreamChatResult {
  /** 本次若自动生成了标题（已 URL 解码），否则为 null */
  generatedTitle: string | null
  citations: KnowledgeCitation[]
  knowledgeStatus: KnowledgeStatus
}

/**
 * 与后端 ChatRequest 对齐的流式请求体。
 * knowledge_filename 仅在有值时放入 JSON，避免传空字符串。
 */
export interface StreamChatRequestBody {
  conversation_id: number
  message: string
  use_knowledge: boolean
  knowledge_filename?: string
}

export interface StreamChatOptions {
  conversationId: number
  message: string
  token: string
  /** 是否启用知识库检索；默认 false，保持普通聊天 */
  useKnowledge?: boolean
  /** 可选，限定检索的 PDF 文件名；空则不传该字段 */
  knowledgeFilename?: string | null
  onChunk: StreamChunkHandler
  onTitle?: StreamTitleHandler
  onCitations?: StreamCitationsHandler
}

function buildStreamChatBody(options: StreamChatOptions): StreamChatRequestBody {
  const body: StreamChatRequestBody = {
    conversation_id: options.conversationId,
    message: options.message,
    use_knowledge: options.useKnowledge === true,
  }

  const filename = options.knowledgeFilename?.trim()
  if (filename) {
    body.knowledge_filename = filename
  }

  return body
}

function parseKnowledgeStatus(raw: string | null): KnowledgeStatus {
  if (raw === 'hit' || raw === 'empty' || raw === 'none') {
    return raw
  }
  return 'none'
}

function parseCitationsHeader(raw: string | null): KnowledgeCitation[] {
  if (!raw) {
    return []
  }

  let decoded = raw
  try {
    decoded = decodeURIComponent(raw)
  } catch {
    decoded = raw
  }

  try {
    const data: unknown = JSON.parse(decoded)
    if (!Array.isArray(data)) {
      return []
    }

    const citations: KnowledgeCitation[] = []
    for (const item of data) {
      if (!item || typeof item !== 'object') {
        continue
      }
      const record = item as Record<string, unknown>
      const filename = record.filename
      if (typeof filename !== 'string' || !filename.trim()) {
        continue
      }

      let page: number | null = null
      if (typeof record.page === 'number' && Number.isFinite(record.page)) {
        page = record.page
      } else if (record.page === null || record.page === undefined) {
        page = null
      }

      const citation: KnowledgeCitation = {
        filename: filename.trim(),
        page,
      }

      if (typeof record.snippet === 'string') {
        citation.snippet = record.snippet
      }
      if (typeof record.distance === 'number') {
        citation.distance = record.distance
      } else if (record.distance === null) {
        citation.distance = null
      }
      if (typeof record.chunk_count === 'number') {
        citation.chunk_count = record.chunk_count
      }

      citations.push(citation)
    }
    return citations
  } catch {
    return []
  }
}

/**
 * 向后端发起流式聊天。
 *
 * 准备阶段成功后，若响应头带有新标题 / 引用，会立刻回调
 *（不依赖流式正文是否完整结束）。
 */
export async function streamChat(
  options: StreamChatOptions,
): Promise<StreamChatResult> {
  const body = buildStreamChatBody(options)

  const response = await fetch(
    'http://127.0.0.1:8000/api/chat/stream',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${options.token}`,
      },
      body: JSON.stringify(body),
    },
  )

  if (!response.ok) {
    let detail = `请求失败：${response.status}`

    try {
      const errorBody = await response.json()
      if (typeof errorBody?.detail === 'string') {
        detail = errorBody.detail
      }
    } catch {
      // 非 JSON 错误体时沿用默认文案
    }

    throw new Error(detail)
  }

  let generatedTitle: string | null = null
  const encodedTitle = response.headers.get(TITLE_HEADER)
  if (encodedTitle) {
    try {
      generatedTitle = decodeURIComponent(encodedTitle)
    } catch {
      generatedTitle = encodedTitle
    }

    options.onTitle?.(generatedTitle)
  }

  const knowledgeStatus = parseKnowledgeStatus(
    response.headers.get(KNOWLEDGE_STATUS_HEADER),
  )
  const citations = parseCitationsHeader(
    response.headers.get(CITATIONS_HEADER),
  )
  options.onCitations?.(citations, knowledgeStatus)

  const reader = response.body?.getReader()

  if (!reader) {
    throw new Error('浏览器不支持流式读取')
  }

  const decoder = new TextDecoder('utf-8')

  while (true) {
    const { done, value } = await reader.read()

    if (done) {
      break
    }

    const text = decoder.decode(value, { stream: true })

    if (text) {
      options.onChunk(text)
    }
  }

  const lastText = decoder.decode()

  if (lastText) {
    options.onChunk(lastText)
  }

  return {
    generatedTitle,
    citations,
    knowledgeStatus,
  }
}

/** 供单测 / 调试核对请求体构造（不发起网络请求）。 */
export { buildStreamChatBody }
