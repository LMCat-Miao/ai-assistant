import request from '@/utils/request'
import type { ApiResponse } from '@/utils/request'
import type { KnowledgeCitation } from '@/api/chat'

/**
 * 单条聊天消息（与后端 messages 表字段对齐）
 */
export interface Message {
  id: number
  conversation_id: number
  role: 'user' | 'assistant'
  content: string
  created_at: string
  /** 检索到的参考来源；普通聊天或旧数据为 null/undefined */
  citations?: KnowledgeCitation[] | null
  /** 前端临时：知识库状态提示（empty 时展示资料不足） */
  knowledgeStatus?: 'none' | 'hit' | 'empty'
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
