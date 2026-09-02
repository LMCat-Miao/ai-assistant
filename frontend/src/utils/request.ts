import axios from 'axios'
import { useUserStore } from '@/stores/user'
import router from '@/router'

const request = axios.create({
  baseURL: 'http://127.0.0.1:8000',
  timeout: 10000,
})


request.interceptors.request.use(
  (config) => {
    const userStore = useUserStore()

    const token = userStore.token

    console.log('请求拦截器拿到的 Token:', token)

    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }

    console.log('最终请求头:', config.headers)

    return config
  },

  (error) => {
    return Promise.reject(error)
  }
)


request.interceptors.response.use(
  (response) => {
    return response
  },

  async (error) => {
    if (error.response?.status === 401) {
      console.log('Token 已失效，需要重新登录')

      const userStore = useUserStore()

      // 清除登录状态
      userStore.logout()

      // 跳转登录页面
      await router.push('/login')
    }

    return Promise.reject(error)
  }
)

export default request