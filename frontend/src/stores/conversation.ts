import { ref } from 'vue'
import { defineStore } from 'pinia'

import {
  getConversations,
  createConversation,
  deleteConversation,
  type Conversation,
} from '@/api/conversation'


export const useConversationStore = defineStore(
  'conversation',
  () => {

    // ==================================================
    // State
    // ==================================================

    /**
     * 当前用户的全部会话
     */
    const conversations =
      ref<Conversation[]>([])

    /**
     * 当前正在查看的会话 ID
     *
     * null 表示当前没有选择任何会话
     */
    const currentConversationId =
      ref<number | null>(null)


    // ==================================================
    // Actions
    // ==================================================

    /**
     * 获取当前用户的全部会话
     */
    const fetchConversations = async () => {
      try {
        const response =
          await getConversations()

        // 保存到 Pinia
        conversations.value =
          response.data

      } catch (error) {
        console.error(
          '获取会话列表失败：',
          error
        )

        throw error
      }
    }


    /**
     * 创建一个新的会话
     */
    const createNewConversation =
      async (title: string) => {

        try {
          // 请求后端创建会话
          const response =
            await createConversation(title)

          // 将新会话加入列表
          conversations.value.push(
            response.data
          )

          // 自动选中新创建的会话
          currentConversationId.value =
            response.data.id

          return response.data

        } catch (error) {
          console.error(
            '创建会话失败：',
            error
          )

          throw error
        }
      }


    /**
     * 删除一个会话
     */
    const removeConversation =
      async (id: number) => {

        try {
          // 1. 删除数据库中的会话
          await deleteConversation(id)

          // 2. 删除 Store 中的会话
          conversations.value =
            conversations.value.filter(
              item => item.id !== id
            )

          // 3. 如果删除的是当前会话
          //    清空当前会话 ID
          if (
            currentConversationId.value === id
          ) {
            currentConversationId.value = null
          }

        } catch (error) {
          console.error(
            '删除会话失败：',
            error
          )

          throw error
        }
      }


    /**
     * 选择一个会话
     */
    const selectConversation = (
      id: number
    ) => {

      currentConversationId.value = id
    }


    // ==================================================
    // 暴露给组件使用
    // ==================================================

    return {
      conversations,
      currentConversationId,

      fetchConversations,
      createNewConversation,
      removeConversation,
      selectConversation,
    }
  }
)

