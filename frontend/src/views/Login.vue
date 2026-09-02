<script setup lang="ts">

import { ref } from 'vue'
import { login } from '@/api/auth'
import { getUserInfo } from '@/api/user'
import { useUserStore } from '@/stores/user'
import router from '@/router'

const username = ref('')
const password = ref('')

const userStore = useUserStore()

const handleLogin = async () => {

  try {

    // ① 登录
    const res = await login(
      username.value,
      password.value
    )

    // ② 获取 Token
    const token = res.data.data.access_token

    // ③ 保存 Token 到 Pinia
    userStore.setToken(token)

    console.log('Token:', token)

    // ④ 获取当前用户信息
    const userRes = await getUserInfo()

    console.log('用户信息:', userRes.data)

    // ⑤ 保存用户信息到 Pinia
    userStore.setUserInfo(userRes.data.data)

    // ⑥ 登录完成，进入 Home
    router.push('/home')

  } catch (error) {

    console.log('登录失败:', error)

  }

}

</script>

<template>

  <div>

    <h1>AI学习助手</h1>

    <input
      v-model="username"
      placeholder="用户名"
    />

    <input
      v-model="password"
      type="password"
      placeholder="密码"
    />

    <button @click="handleLogin">
      登录
    </button>

  </div>

</template>