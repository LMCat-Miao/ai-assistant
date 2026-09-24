import request from '@/utils/request'
import type { ApiResponse } from '@/utils/request'

/**
 * 会话列表中的单条会话。
 * 字段与后端 GET /conversations 返回的 data 项对齐。
 */
export interface Conversation {
  id: number
  title: string
  user_id?: number
  created_at?: string
  updated_at?: string
}

/**
 * 创建会话成功后，后端 data 的结构。
 * 注意：这里是 conversation_id，不是 id。
 */
export interface CreateConversationResult {
  conversation_id: number
  title: string
}

/**
 * 获取当前用户的全部会话
 *
 * 实际路径：GET /conversations
 *（后端 prefix 是 /conversations，没有 /api）
 */
export function getConversations() {
  return request.get<ApiResponse<Conversation[]>>('/conversations')
}

/**
 * 创建一个新的会话
 *
 * 实际路径：POST /conversations/
 * 当前后端忽略请求体，标题固定为「新会话」。
 * 保留可选 title 参数，方便以后后端支持自定义标题。
 */
export function createConversation(_title?: string) {
  return request.post<ApiResponse<CreateConversationResult>>(
    '/conversations/',
  )
}

/**
 * 删除指定会话
 *
 * 实际路径：DELETE /conversations/{id}
 * 成功时后端返回 { code, message, data: null }
 */
export function deleteConversation(id: number) {
  return request.delete<ApiResponse<null>>(`/conversations/${id}`)
}
