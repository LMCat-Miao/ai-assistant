
import request from '@/utils/request'

/**
 * 会话数据结构
 */
export interface Conversation {
  id: number
  title: string
}

/**
 * 获取当前用户的全部会话
 */
export function getConversations() {
  return request.get<Conversation[]>('/api/conversations')
}

/**
 * 创建一个新的会话
 */
export function createConversation(title: string) {
  return request.post('/api/conversations', {
    title,
  })
}

/**
 * 删除指定会话
 */
export function deleteConversation(id: number) {
  return request.delete(`/api/conversations/${id}`)
}

