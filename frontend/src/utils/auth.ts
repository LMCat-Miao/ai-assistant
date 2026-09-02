import axios from "axios"
import { useUserStore } from "@/stores/user"

const request = axios.create({
  baseURL: "http://127.0.0.1:8000",
  timeout: 10000,
})


// 请求拦截器
request.interceptors.request.use((config) => {

  const userStore = useUserStore()

  const token = userStore.token

  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }

  return config
})


export default request