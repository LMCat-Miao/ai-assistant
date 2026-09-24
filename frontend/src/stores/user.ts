import { defineStore } from 'pinia'
import { clearConversationSessionSync } from '@/stores/clearConversationSession'

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

    /**
     * 退出登录：同步清认证 + 会话内存/持久化，再由页面跳转登录页。
     * 不再使用动态 import，避免 reset 晚于 removeItem 后又被 persist 写回。
     */
    logout() {
      this.token = ''
      this.userInfo = null
      clearConversationSessionSync()
    },
  },
  persist: true,
})
