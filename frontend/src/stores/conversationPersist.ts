/**
 * conversation Store 持久化用的 key 与 storage。
 * 抽成独立文件，避免 user ↔ conversation 循环依赖。
 */

/** 与 pinia persist.key 保持一致 */
export const CONVERSATION_PERSIST_KEY = 'conversation'

type PersistedConversationSlice = {
  currentConversationId?: number | null
  ownerUserId?: string | null
}

/**
 * 判断是否为「已清空」的会话持久化快照。
 * 清空后不应再在 Local Storage 中保留该键。
 */
export function isEmptyConversationPersistPayload(
  value: string,
): boolean {
  try {
    const parsed = JSON.parse(value) as PersistedConversationSlice
    const id = parsed.currentConversationId
    const owner = parsed.ownerUserId
    return (
      (id === null || id === undefined) &&
      (owner === null || owner === undefined)
    )
  } catch {
    return false
  }
}

/**
 * 自定义 storage：
 * 当 currentConversationId / ownerUserId 均为空时，删除 key，
 * 避免 logout → reset 后 persist 插件把空对象重新写入 Local Storage。
 */
export const conversationPersistStorage = {
  getItem(key: string): string | null {
    return localStorage.getItem(key)
  },

  setItem(key: string, value: string): void {
    if (isEmptyConversationPersistPayload(value)) {
      localStorage.removeItem(key)
      return
    }
    localStorage.setItem(key, value)
  },

  removeItem(key: string): void {
    localStorage.removeItem(key)
  },
}
