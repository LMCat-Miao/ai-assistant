<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { useUserStore } from '@/stores/user'
import { renderMarkdown } from '@/utils/markdown'
interface Message {
  role: 'user' | 'assistant'
  content: string
}

const userStore = useUserStore()

// 当前输入框内容
const message = ref('')

// 聊天消息列表
const messages = ref<Message[]>([])

// 是否正在请求 AI
const loading = ref(false)

// 聊天消息容器
const messagesContainer = ref<HTMLElement | null>(null)

/**
 * 自动滚动到底部
 */
const scrollToBottom = async () => {
  await nextTick()

  if (messagesContainer.value) {
    messagesContainer.value.scrollTop =
      messagesContainer.value.scrollHeight
  }
}

/**
 * 发送消息
 */
const handleSend = async () => {
  // 防止发送空消息
  if (!message.value.trim()) return

  // 防止重复发送
  if (loading.value) return

  // 保存用户输入
  const userMessage = message.value.trim()

  // 清空输入框
  message.value = ''

  // 添加用户消息
  messages.value.push({
    role: 'user',
    content: userMessage,
  })

  // 自动滚动
  await scrollToBottom()

  loading.value = true

  try {
    const MAX_CONTEXT_MESSAGES = 20

    const chatMessages = messages.value
      .slice(-MAX_CONTEXT_MESSAGES)
      .map((item) => ({
        role: item.role,
        content: item.content,
      }))

    const response = await fetch(
      'http://127.0.0.1:8000/api/chat/stream',
      {
        method: 'POST',

        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${userStore.token}`,
        },

        body: JSON.stringify({
          messages: chatMessages,
        }),
      }
    )

    if (!response.ok) {
      throw new Error(`请求失败：${response.status}`)
    }

    // 获取流
    const reader = response.body?.getReader()

    if (!reader) {
      throw new Error('浏览器不支持流式读取')
    }

    const decoder = new TextDecoder('utf-8')

    // 添加 AI 消息
    messages.value.push({
      role: 'assistant',
      content: '',
    })

    // 获取最后一条消息
    const assistantMessage =
      messages.value[messages.value.length - 1]

    // 持续读取 AI 返回的数据
    while (true) {
      const { done, value } = await reader.read()

      if (done) break

      const text = decoder.decode(value, {
        stream: true,
      })

      // 拼接 AI 内容
      assistantMessage.content += text

      // AI 每输出一段，都滚动到底部
      await scrollToBottom()
    }

    // 处理 decoder 最后可能残留的数据
    const lastText = decoder.decode()

    if (lastText) {
      assistantMessage.content += lastText
    }

  } catch (error) {
    console.error('AI流式请求失败：', error)

    messages.value.push({
      role: 'assistant',
      content: '抱歉，AI 请求失败，请稍后重试。',
    })

  } finally {
    loading.value = false

    await scrollToBottom()
  }
}
</script>

<template>
  <div class="chat-page">

    <h1>AI 学习助手</h1>

    <!-- 消息区域 -->
    <div
      ref="messagesContainer"
      class="messages-container"
    >
      <div
        v-for="(item, index) in messages"
        :key="index"
        class="message"
        :class="item.role"
      >
        <div class="message-role">
          {{ item.role === 'user' ? '我' : 'AI' }}
        </div>

        <div class="message-content"
        v-html="renderMarkdown(item.content)"
        >
      </div>
      </div>
    </div>

    <!-- 输入区域 -->
    <div class="input-area">

      <input
        v-model="message"
        placeholder="请输入你的问题"
        @keyup.enter="handleSend"
      />

      <button
        :disabled="loading"
        @click="handleSend"
      >
        {{ loading ? '思考中...' : '发送' }}
      </button>

    </div>

  </div>
</template>

<style scoped>
.chat-container {
  width: 800px;
  margin: 40px auto;
}

.answer {
  min-height: 200px;
  padding: 20px;
  margin: 20px 0;
  border: 1px solid #ddd;
  border-radius: 8px;
  white-space: pre-wrap;
}

.input-area {
  display: flex;
  gap: 10px;
}

.input-area input {
  flex: 1;
  padding: 10px;
}

.input-area button {
  padding: 10px 20px;
}
</style>