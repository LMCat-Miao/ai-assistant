<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import axios from 'axios'

import { login } from '@/api/auth'
import { getUserInfo } from '@/api/user'
import { useUserStore } from '@/stores/user'
import router from '@/router'

const route = useRoute()
const userStore = useUserStore()
const formRef = ref<FormInstance>()
const loggingIn = ref(false)

const form = reactive({
  username: '',
  password: '',
})

function utf8ByteLength(value: string): number {
  return new TextEncoder().encode(value).length
}

const rules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    {
      validator: (_rule, value: string, callback) => {
        if (!value || !String(value).trim()) {
          callback(new Error('用户名不能为空'))
          return
        }
        callback()
      },
      trigger: 'blur',
    },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    {
      min: 6,
      message: '密码长度至少 8 个字符',
      trigger: 'blur',
    },
    {
      validator: (_rule, value: string, callback) => {
        if (!value) {
          callback()
          return
        }
        if (utf8ByteLength(value) > 72) {
          callback(new Error('密码过长（UTF-8 编码后不能超过 72 字节）'))
          return
        }
        callback()
      },
      trigger: 'blur',
    },
  ],
}

function extractErrorMessage(error: unknown, fallback: string): string {
  if (!axios.isAxiosError(error)) {
    return fallback
  }
  const data = error.response?.data as
    | { message?: string; detail?: unknown }
    | undefined
  if (data && typeof data.message === 'string' && data.message) {
    return data.message
  }
  const detail = data?.detail
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string }
    if (first?.msg) {
      return first.msg
    }
  }
  if (typeof detail === 'string') {
    return detail
  }
  return fallback
}

onMounted(() => {
  if (route.query.registered === '1') {
    ElMessage.success('注册成功，请使用用户名和密码登录')
  }
})

async function handleLogin() {
  if (loggingIn.value) {
    return
  }

  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) {
    return
  }

  loggingIn.value = true
  // 仅当本流程已 setToken 后，catch 才 logout，避免误清其他会话状态
  let tokenWritten = false
  try {
    const res = await login(form.username.trim(), form.password)
    const body = res.data

    // 后端业务失败也可能 HTTP 200（如 code=401），必须先判业务码
    if (body.code !== 200) {
      ElMessage.error(body.message || '登录失败')
      return
    }

    const token = body.data?.access_token
    if (!token || typeof token !== 'string') {
      ElMessage.error('登录成功但未返回有效 Token，请稍后重试')
      return
    }

    userStore.setToken(token)
    tokenWritten = true

    const userRes = await getUserInfo()
    const userBody = userRes.data
    if (userBody.code !== 200 || userBody.data == null) {
      ElMessage.error(userBody.message || '获取用户信息失败，请重新登录')
      userStore.logout()
      return
    }

    userStore.setUserInfo(userBody.data)
    await router.push('/chat')
  } catch (error) {
    if (tokenWritten) {
      userStore.logout()
    }
    ElMessage.error(extractErrorMessage(error, '登录失败'))
  } finally {
    loggingIn.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <h1 class="title">AI 学习助手</h1>
      <p class="subtitle">登录账号</p>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        size="large"
        @submit.prevent
      >
        <el-form-item label="用户名" prop="username">
          <el-input
            v-model="form.username"
            placeholder="请输入用户名"
            autocomplete="username"
            :disabled="loggingIn"
          />
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            placeholder="请输入密码"
            autocomplete="current-password"
            :disabled="loggingIn"
            @keyup.enter="handleLogin"
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            class="submit-btn"
            :loading="loggingIn"
            :disabled="loggingIn"
            @click="handleLogin"
          >
            登录
          </el-button>
        </el-form-item>
      </el-form>

      <p class="footer-link">
        还没有账号？
        <router-link to="/register">立即注册</router-link>
      </p>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background:
    radial-gradient(ellipse at top, rgba(170, 59, 255, 0.08), transparent 55%),
    var(--bg, #fff);
}

.login-card {
  width: 100%;
  max-width: 420px;
  padding: 32px 28px 24px;
  border: 1px solid var(--border, #e5e4e7);
  border-radius: 12px;
  background: var(--bg, #fff);
  box-shadow: var(--shadow, 0 10px 15px -3px rgba(0, 0, 0, 0.08));
}

.title {
  margin: 0;
  font-size: 1.6rem;
  color: var(--text-h, #08060d);
  text-align: center;
}

.subtitle {
  margin: 8px 0 24px;
  text-align: center;
  color: var(--text, #6b6375);
  font-size: 0.95rem;
}

.submit-btn {
  width: 100%;
}

.footer-link {
  margin: 8px 0 0;
  text-align: center;
  color: var(--text, #6b6375);
  font-size: 0.9rem;
}

.footer-link a {
  color: var(--accent, #aa3bff);
  text-decoration: none;
}

.footer-link a:hover {
  text-decoration: underline;
}
</style>
