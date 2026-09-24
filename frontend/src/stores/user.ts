import { defineStore } from 'pinia'

export const useUserStore = defineStore('user', {
  state: () => ({
    token: '',
    userInfo: null as { user_id?: string; username?: string } | null,
  }),

  getters: {
    isLogin: (state) => !!state.token,
  },

  actions: {
    setToken(token: string) {
      this.token = token
    },

    setUserInfo(userInfo: { user_id?: string; username?: string } | null) {
      this.userInfo = userInfo
    },

    logout() {
      this.token = ''
      this.userInfo = null

      // 同步清除 conversation Store 的持久化，避免异步 reset 尚未完成时
      // 刷新/再登录读到上一用户的 currentConversationId
      try {
        localStorage.removeItem('conversation')
      } catch {
        // 忽略隐私模式等导致的 storage 异常
      }

      // 再异步 reset 内存中的 Store（避免与 request.ts 顶层循环依赖）
      void import('@/stores/conversation').then(({ useConversationStore }) => {
        useConversationStore().reset()
      })
    },
  },
  persist: true,
})
