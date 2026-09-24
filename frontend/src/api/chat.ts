/**
 * 流式聊天 API。
 *
 * 使用 fetch + ReadableStream，而不是 Axios：
 * Axios 对文本流支持较弱，项目里原本就用 fetch。
 */

export type StreamChunkHandler = (chunk: string) => void
export type StreamTitleHandler = (title: string) => void

/** 与后端 chat.py 中 TITLE_HEADER 保持一致 */
const TITLE_HEADER = 'X-Conversation-Title'

export interface StreamChatResult {
  /** 本次若自动生成了标题（已 URL 解码），否则为 null */
  generatedTitle: string | null
}

/**
 * 向后端发起流式聊天。
 *
 * 只提交 conversation_id 和当前 message。
 * 准备阶段成功后，若响应头带有新标题，会立刻通过 onTitle 回调
 *（此时用户消息已入库、标题已落库；不依赖流式是否完整结束）。
 */
export async function streamChat(
  conversationId: number,
  message: string,
  token: string,
  onChunk: StreamChunkHandler,
  onTitle?: StreamTitleHandler,
): Promise<StreamChatResult> {
  const response = await fetch(
    'http://127.0.0.1:8000/api/chat/stream',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        conversation_id: conversationId,
        message,
      }),
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

    onTitle?.(generatedTitle)
  }

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
      onChunk(text)
    }
  }

  const lastText = decoder.decode()

  if (lastText) {
    onChunk(lastText)
  }

  return { generatedTitle }
}
