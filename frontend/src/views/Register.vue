<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import axios from 'axios'

import { register, sendRegisterCode } from '@/api/auth'

const router = useRouter()
const formRef = ref<FormInstance>()

const form = reactive({
  email: '',
  code: '',
  username: '',
  password: '',
  confirmPassword: '',
})

const sendingCode = ref(false)
const submitting = ref(false)
const countdown = ref(0)
let countdownTimer: ReturnType<typeof setInterval> | null = null

const codeButtonLabel = computed(() =>
  countdown.value > 0 ? `${countdown.value}s 后重试` : '获取验证码',
)

function clearCountdownTimer() {
  if (countdownTimer !== null) {
    clearInterval(countdownTimer)
    countdownTimer = null
  }
}

function startCountdown(seconds = 60) {
  clearCountdownTimer()
  countdown.value = seconds
  countdownTimer = setInterval(() => {
    countdown.value -= 1
    if (countdown.value <= 0) {
      clearCountdownTimer()
      countdown.value = 0
    }
  }, 1000)
}

onBeforeUnmount(() => {
  clearCountdownTimer()
})

function utf8ByteLength(value: string): number {
  return new TextEncoder().encode(value).length
}

const rules: FormRules = {
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    {
      type: 'email',
      message: '请输入有效的邮箱地址',
      trigger: ['blur', 'change'],
    },
  ],
  code: [
    { required: true, message: '请输入验证码', trigger: 'blur' },
    {
      pattern: /^\d{6}$/,
      message: '验证码须为 6 位数字',
      trigger: 'blur',
    },
  ],
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    {
      min: 1,
      max: 64,
      message: '用户名长度为 1～64 个字符',
      trigger: 'blur',
    },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    {
      min: 8,
      max: 72,
      message: '密码长度为 8～72 个字符',
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
  confirmPassword: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    {
      validator: (_rule, value: string, callback) => {
        if (value !== form.password) {
          callback(new Error('两次输入的密码不一致'))
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
  // FastAPI 422
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

async function handleSendCode() {
  if (sendingCode.value || countdown.value > 0) {
    return
  }

  try {
    await formRef.value?.validateField('email')
  } catch {
    return
  }

  sendingCode.value = true
  try {
    const res = await sendRegisterCode({
      email: form.email.trim(),
    })
    const body = res.data

    if (body.code === 200) {
      ElMessage.success(body.message || '验证码已发送')
      startCountdown(60)
      return
    }

    if (body.code === 429) {
      ElMessage.warning(body.message || '发送过于频繁，请稍后再试')
      return
    }

    if (body.code === 503) {
      ElMessage.error(body.message || '验证码服务暂不可用，请稍后重试')
      return
    }

    ElMessage.error(body.message || '发送验证码失败')
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, '发送验证码失败'))
  } finally {
    sendingCode.value = false
  }
}

async function handleRegister() {
  if (submitting.value) {
    return
  }

  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) {
    return
  }

  submitting.value = true
  try {
    const res = await register({
      email: form.email.trim(),
      code: form.code.trim(),
      username: form.username.trim(),
      password: form.password,
    })
    const body = res.data

    if (body.code === 200) {
      ElMessage.success(body.message || '注册成功，请登录')
      // 不写 Token、不拉用户信息；仅跳转登录
      await router.push({
        path: '/login',
        query: { registered: '1' },
      })
      return
    }

    ElMessage.error(body.message || '注册失败')
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, '注册失败'))
  } finally {
    submitting.value = false
  }
}

function goLogin() {
  router.push('/login')
}
</script>

<template>
  <div class="register-page">
    <div class="register-card">
      <h1 class="title">AI 学习助手</h1>
      <p class="subtitle">创建账号</p>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        size="large"
        @submit.prevent
      >
        <el-form-item label="邮箱" prop="email">
          <el-input
            v-model="form.email"
            placeholder="请输入邮箱"
            autocomplete="email"
          />
        </el-form-item>

        <el-form-item label="验证码" prop="code">
          <div class="code-row">
            <el-input
              v-model="form.code"
              placeholder="6 位数字验证码"
              maxlength="6"
              autocomplete="one-time-code"
            />
            <el-button
              type="primary"
              plain
              :loading="sendingCode"
              :disabled="countdown > 0 || sendingCode"
              @click="handleSendCode"
            >
              {{ codeButtonLabel }}
            </el-button>
          </div>
        </el-form-item>

        <el-form-item label="用户名" prop="username">
          <el-input
            v-model="form.username"
            placeholder="1～64 个字符"
            maxlength="64"
            autocomplete="username"
          />
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            placeholder="8～72 个字符"
            autocomplete="new-password"
          />
        </el-form-item>

        <el-form-item label="确认密码" prop="confirmPassword">
          <el-input
            v-model="form.confirmPassword"
            type="password"
            show-password
            placeholder="再次输入密码"
            autocomplete="new-password"
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            class="submit-btn"
            :loading="submitting"
            :disabled="submitting"
            @click="handleRegister"
          >
            注册
          </el-button>
        </el-form-item>
      </el-form>

      <p class="footer-link">
        已有账号？
        <a href="javascript:void(0)" @click="goLogin">返回登录</a>
      </p>
    </div>
  </div>
</template>

<style scoped>
.register-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background:
    radial-gradient(ellipse at top, rgba(170, 59, 255, 0.08), transparent 55%),
    var(--bg, #fff);
}

.register-card {
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

.code-row {
  display: flex;
  gap: 10px;
  width: 100%;
}

.code-row .el-input {
  flex: 1;
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
