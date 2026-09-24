/**
 * 同步清理会话 Store 内存状态与 Local Storage。
 * 供 logout / 401 使用，不依赖动态 import。
 */
import { getActivePinia } from 'pinia'
import { CONVERSATION_PERSIST_KEY } from '@/stores/conversationPersist'

type ConversationStoreLike = {
  reset: () => void
}

export function clearConversationSessionSync(): void {
  const pinia = getActivePinia()

  // Pinia 内部 store 映射；logout 时 conversation store 通常已创建
  const rawStore = pinia?._s.get('conversation') as
    | ConversationStoreLike
    | undefined

  if (rawStore && typeof rawStore.reset === 'function') {
    // 先清空内存；persist 若触发写入，会由自定义 storage 删除空快照
    rawStore.reset()
  }

  // 再强制删除键，防止插件异步补写或旧数据残留
  try {
    localStorage.removeItem(CONVERSATION_PERSIST_KEY)
  } catch {
    // 忽略隐私模式等异常
  }
}
