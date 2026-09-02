<script setup lang="ts">
import { useUserStore } from '@/stores/user'
import router from '@/router'

const userStore = useUserStore()

const handleLogout = () => {
  userStore.logout()

  router.push('/login')
}
</script>

<template>
  <div>
    <h1>
      欢迎回来，{{ userStore.userInfo?.username }}
    </h1>

    <p v-if="userStore.isLogin">
      今天也要学习奥
    </p>

    <button @click="handleLogout">
      退出登录
    </button>
  </div>
</template>