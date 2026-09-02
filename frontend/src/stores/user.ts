import { defineStore } from 'pinia'

export const useUserStore = defineStore('user', {
  state: () => ({
    token: '',
    userInfo: null,
  }),

  getters: {
    isLogin: (state) => !!state.token,
  },

  actions: {
    setToken(token: string) {
      this.token = token
    },

    setUserInfo(userInfo: any) {
      this.userInfo = userInfo
    },

    logout() {
      this.token = ''
      this.userInfo = null
    },
  },
  persist: true,
})