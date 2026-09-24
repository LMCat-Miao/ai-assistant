import request from '@/utils/request'
import type { ApiResponse } from '@/utils/request'

/**
 * 单条聊天消息（与后端 messages 表字段对齐）
 */
export interface Message {
  id: number
  conversation_id: number
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

/**
 * 获取指定会话的历史消息
 *
 * 实际路径：GET /conversations/{conversationId}/messages
 */
export function getMessages(conversationId: number) {
  return request.get<ApiResponse<Message[]>>(
    `/conversations/${conversationId}/messages`,
  )
}
