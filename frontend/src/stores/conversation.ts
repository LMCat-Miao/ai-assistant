import { ref } from 'vue'
import { defineStore } from 'pinia'

import {
  getConversations,
  createConversation,
  deleteConversation,
  type Conversation,
} from '@/api/conversation'
import { getMessages, type Message } from '@/api/message'
import { useUserStore } from '@/stores/user'
import {
  CONVERSATION_PERSIST_KEY,
  conversationPersistStorage,
} from '@/stores/conversationPersist'

/**
 * 从 Axios 完整响应中安全取出业务 data。
 *
 * 后端约定：{ code, message, data }
 * Axios：response.data === 上述整包
 */
function extractData<T>(
  body: { code: number; message: string; data: T },
): T {
  if (body.code !== 200) {
    throw new Error(body.message || '请求失败')
  }

  return body.data
}

export const useConversationStore = defineStore(
  'conversation',
  () => {
    // ==================================================
    // State
    // ==================================================

    /** 当前用户的会话列表 */
    const conversations = ref<Conversation[]>([])

    /**
     * 当前选中的会话 ID；null 表示尚未选中。
     * 会持久化到 localStorage，用于刷新后恢复。
     */
    const currentConversationId = ref<number | null>(null)

    /**
     * 持久化 ID 所属的用户（JWT sub）。
     * 用于避免用户 A 的会话 ID 被用户 B 错误恢复。
     */
    const ownerUserId = ref<string | null>(null)

    /** 当前会话的消息列表（不持久化，避免脏缓存） */
    const messages = ref<Message[]>([])

    const conversationsLoading = ref(false)
    const messagesLoading = ref(false)
    const error = ref<string | null>(null)
    const deleting = ref(false)

    /**
     * 用于避免快速切换会话时的竞态：
     * 较晚发起的 loadMessages 才能更新 messages。
     */
    let messagesRequestSerial = 0

    /**
     * 会话「世代」：logout/reset 时递增。
     * 进行中的流式回调若世代不匹配，则丢弃，避免写回旧状态。
     */
    const sessionGeneration = ref(0)

    /** 把当前登录用户记为会话归属，配合持久化防串号 */
    const bindOwnerToCurrentUser = () => {
      const userStore = useUserStore()
      const uid = userStore.userInfo?.user_id
      ownerUserId.value =
        uid === undefined || uid === null ? null : String(uid)
    }

    /** 未登录时禁止再改会话相关状态（防退出后异步回调污染） */
    const canMutateSession = (): boolean => {
      return !!useUserStore().token
    }

    // ==================================================
    // Actions
    // ==================================================

    /**
     * 清空会话相关状态（退出登录时调用）。
     * 递增 sessionGeneration，作废进行中的异步写回。
     */
    const reset = () => {
      sessionGeneration.value += 1
      conversations.value = []
      currentConversationId.value = null
      ownerUserId.value = null
      messages.value = []
      conversationsLoading.value = false
      messagesLoading.value = false
      error.value = null
      deleting.value = false
      messagesRequestSerial += 1
    }

    /**
     * 拉取列表后，按规则恢复或选择默认会话。
     *
     * 1. 持久化 ID 属于当前用户且仍在列表中 → 恢复并加载历史
     * 2. 否则列表非空 → 选第一项
     * 3. 列表为空 → 保持未选中（不自动创建）
     */
    const restoreOrSelectDefault = async (): Promise<void> => {
      const userStore = useUserStore()
      const currentUserId =
        userStore.userInfo?.user_id === undefined ||
        userStore.userInfo?.user_id === null
          ? null
          : String(userStore.userInfo.user_id)

      const savedId = currentConversationId.value
      const list = conversations.value

      let ownerMatches =
        ownerUserId.value !== null &&
        currentUserId !== null &&
        ownerUserId.value === currentUserId

      /**
       * 兼容旧持久化：只有 currentConversationId、尚无 ownerUserId。
       * 若 ID 仍在当前用户列表中，则补写归属并允许恢复，
       * 避免升级后误清有效会话、无条件跳到列表第一项。
       */
      if (
        !ownerMatches &&
        ownerUserId.value === null &&
        currentUserId !== null &&
        savedId !== null &&
        list.some((item) => item.id === savedId)
      ) {
        ownerUserId.value = currentUserId
        ownerMatches = true
      }

      // 跨用户：丢弃持久化 ID，避免串会话
      if (!ownerMatches) {
        currentConversationId.value = null
        ownerUserId.value = null
      }

      if (list.length === 0) {
        currentConversationId.value = null
        messages.value = []
        messagesRequestSerial += 1
        return
      }

      const savedStillExists =
        ownerMatches &&
        savedId !== null &&
        list.some((item) => item.id === savedId)

      if (savedStillExists && savedId !== null) {
        await selectConversation(savedId)
        return
      }

      // 无有效持久化 ID：才退回列表第一项
      await selectConversation(list[0].id)
    }

    const fetchConversations = async (): Promise<Conversation[]> => {
      conversationsLoading.value = true
      error.value = null

      try {
        const response = await getConversations()
        const list = extractData(response.data)

        conversations.value = Array.isArray(list) ? list : []
        return conversations.value
      } catch (err) {
        const message =
          err instanceof Error ? err.message : '获取会话列表失败'
        error.value = message
        console.error('获取会话列表失败：', err)
        throw err
      } finally {
        conversationsLoading.value = false
      }
    }

    const createNewConversation = async (
      title?: string,
    ): Promise<Conversation> => {
      error.value = null

      try {
        const response = await createConversation(title)
        const created = extractData(response.data)

        const newConversation: Conversation = {
          id: created.conversation_id,
          title: created.title,
        }

        conversations.value = [
          newConversation,
          ...conversations.value,
        ]

        currentConversationId.value = newConversation.id
        bindOwnerToCurrentUser()
        messages.value = []
        messagesRequestSerial += 1

        return newConversation
      } catch (err) {
        const message =
          err instanceof Error ? err.message : '创建会话失败'
        error.value = message
        console.error('创建会话失败：', err)
        throw err
      }
    }

    const loadMessages = async (
      conversationId: number,
    ): Promise<Message[]> => {
      const requestSerial = ++messagesRequestSerial

      messagesLoading.value = true
      error.value = null

      try {
        const response = await getMessages(conversationId)
        const list = extractData(response.data)
        const nextMessages = Array.isArray(list) ? list : []

        if (requestSerial !== messagesRequestSerial) {
          return nextMessages
        }

        if (currentConversationId.value !== conversationId) {
          return nextMessages
        }

        messages.value = nextMessages
        return nextMessages
      } catch (err) {
        if (requestSerial === messagesRequestSerial) {
          const message =
            err instanceof Error ? err.message : '获取历史消息失败'
          error.value = message
        }

        console.error('获取历史消息失败：', err)
        throw err
      } finally {
        if (requestSerial === messagesRequestSerial) {
          messagesLoading.value = false
        }
      }
    }

    const selectConversation = async (id: number): Promise<void> => {
      currentConversationId.value = id
      bindOwnerToCurrentUser()
      messages.value = []

      await loadMessages(id)
    }

    const removeConversation = async (id: number): Promise<void> => {
      if (deleting.value) {
        return
      }

      deleting.value = true
      error.value = null

      try {
        const response = await deleteConversation(id)
        extractData(response.data)

        conversations.value = conversations.value.filter(
          (item) => item.id !== id,
        )

        // 删的不是当前会话：不动 currentConversationId
        if (currentConversationId.value !== id) {
          return
        }

        messages.value = []
        currentConversationId.value = null
        messagesRequestSerial += 1

        const next = conversations.value[0]
        if (next) {
          await selectConversation(next.id)
        } else {
          ownerUserId.value = null
        }
      } catch (err) {
        let message = '删除会话失败'

        if (err && typeof err === 'object' && 'response' in err) {
          const axiosErr = err as {
            response?: { data?: { detail?: string; message?: string } }
          }
          message =
            axiosErr.response?.data?.detail ||
            axiosErr.response?.data?.message ||
            message
        } else if (err instanceof Error) {
          message = err.message
        }

        error.value = message
        console.error('删除会话失败：', err)
        throw err
      } finally {
        deleting.value = false
      }
    }

    /**
     * 用后端返回的新标题同步侧栏（不单独发请求）。
     * 按 conversationId 更新，避免更新错会话。
     */
    const updateConversationTitleLocally = (
      conversationId: number,
      title: string,
    ) => {
      if (!canMutateSession()) {
        return
      }

      const trimmed = title.trim()
      if (!trimmed) {
        return
      }

      const target = conversations.value.find(
        (item) => item.id === conversationId,
      )
      if (!target) {
        return
      }

      target.title = trimmed

      conversations.value = [
        target,
        ...conversations.value.filter((item) => item.id !== conversationId),
      ]
    }

    const appendMessage = (message: Message) => {
      if (!canMutateSession()) {
        return
      }
      messages.value.push(message)
    }

    const updateLastMessageContent = (content: string) => {
      if (!canMutateSession()) {
        return
      }

      const last = messages.value[messages.value.length - 1]
      if (
        last &&
        currentConversationId.value !== null &&
        last.conversation_id === currentConversationId.value
      ) {
        last.content = content
      }
    }

    return {
      conversations,
      currentConversationId,
      ownerUserId,
      messages,
      conversationsLoading,
      messagesLoading,
      error,
      deleting,
      sessionGeneration,

      reset,
      fetchConversations,
      restoreOrSelectDefault,
      createNewConversation,
      selectConversation,
      loadMessages,
      removeConversation,
      updateConversationTitleLocally,
      appendMessage,
      updateLastMessageContent,
    }
  },
  {
    persist: {
      key: CONVERSATION_PERSIST_KEY,
      pick: ['currentConversationId', 'ownerUserId'],
      storage: conversationPersistStorage,
    },
  },
)
