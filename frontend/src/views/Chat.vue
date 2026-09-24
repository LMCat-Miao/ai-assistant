<script setup lang="ts">
/**
 * AI 学习助手聊天工作台。
 *
 * 职责：布局编排、会话操作、流式发送。
 * 展示拆到子组件；状态来自 Pinia conversation / user Store。
 */
import { computed, nextTick, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'

import ChatHeader from '@/components/chat/ChatHeader.vue'
import ConversationSidebar from '@/components/chat/ConversationSidebar.vue'
import MessagePanel from '@/components/chat/MessagePanel.vue'
import ChatComposer from '@/components/chat/ChatComposer.vue'

import { streamChat } from '@/api/chat'
import type { Message } from '@/api/message'
import { useConversationStore } from '@/stores/conversation'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()
const conversationStore = useConversationStore()

const draft = ref('')
const streaming = ref(false)
const creating = ref(false)

/** 消息滚动容器 */
const scrollContainer = ref<HTMLElement | null>(null)

/**
 * 用户是否仍停留在底部附近。
 * 向上翻看历史时为 false，避免流式输出强行打断阅读。
 */
const stickToBottom = ref(true)

const currentTitle = computed(() => {
  const id = conversationStore.currentConversationId
  if (id === null) {
    return '未选择会话'
  }

  const found = conversationStore.conversations.find((item) => item.id === id)
  return found?.title || '新会话'
})

const username = computed(
  () => userStore.userInfo?.username || '用户',
)

const hasConversation = computed(
  () => conversationStore.currentConversationId !== null,
)

const isNearBottom = (el: HTMLElement): boolean => {
  const distance = el.scrollHeight - el.scrollTop - el.clientHeight
  return distance < 80
}

const onScroll = () => {
  const el = scrollContainer.value
  if (!el) {
    return
  }

  stickToBottom.value = isNearBottom(el)
}

const scrollToBottom = async (force = false) => {
  await nextTick()

  const el = scrollContainer.value
  if (!el) {
    return
  }

  if (force || stickToBottom.value) {
    el.scrollTop = el.scrollHeight
  }
}

/** 生成临时消息 ID（流式阶段尚未拿到后端 id） */
let tempId = -1
const nextTempId = () => {
  tempId -= 1
  return tempId
}

const buildLocalMessage = (
  role: Message['role'],
  content: string,
  conversationId: number,
): Message => ({
  id: nextTempId(),
  conversation_id: conversationId,
  role,
  content,
  created_at: new Date().toISOString(),
})

const handleLogout = () => {
  userStore.logout()
  router.push('/login')
}

const handleCreate = async () => {
  if (creating.value || streaming.value) {
    return
  }

  creating.value = true

  try {
    await conversationStore.createNewConversation()
    stickToBottom.value = true
    await scrollToBottom(true)
    ElMessage.success('已创建新对话')
  } catch {
    ElMessage.error(conversationStore.error || '创建会话失败')
  } finally {
    creating.value = false
  }
}

const handleSelect = async (id: number) => {
  if (streaming.value) {
    ElMessage.warning('请等待当前回答生成完成后再切换会话')
    return
  }

  if (id === conversationStore.currentConversationId) {
    return
  }

  try {
    await conversationStore.selectConversation(id)
    stickToBottom.value = true
    await scrollToBottom(true)
  } catch {
    ElMessage.error(conversationStore.error || '切换会话失败')
  }
}

const handleRemove = async (id: number) => {
  if (conversationStore.deleting || streaming.value) {
    return
  }

  try {
    await ElMessageBox.confirm(
      '删除后该会话及其聊天记录将无法恢复。确定删除吗？',
      '删除会话',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
  } catch {
    return
  }

  try {
    await conversationStore.removeConversation(id)
    stickToBottom.value = true
    await scrollToBottom(true)
    ElMessage.success('会话已删除')
  } catch {
    ElMessage.error(conversationStore.error || '删除会话失败')
  }
}

/**
 * 发送消息：
 * 1. 若无当前会话则先创建
 * 2. 本地追加 user / assistant 占位
 * 3. 只把 conversation_id + message 交给流式接口
 */
const handleSend = async (preset?: string) => {
  const text = (preset ?? draft.value).trim()

  if (!text || streaming.value) {
    return
  }

  draft.value = ''
  streaming.value = true
  stickToBottom.value = true

  try {
    let conversationId = conversationStore.currentConversationId

    if (conversationId === null) {
      const created = await conversationStore.createNewConversation()
      conversationId = created.id
    }

    conversationStore.appendMessage(
      buildLocalMessage('user', text, conversationId),
    )
    await scrollToBottom(true)

    conversationStore.appendMessage(
      buildLocalMessage('assistant', '', conversationId),
    )

    let assistantContent = ''

    await streamChat(
      conversationId,
      text,
      userStore.token,
      async (chunk) => {
        assistantContent += chunk
        conversationStore.updateLastMessageContent(assistantContent)
        await scrollToBottom(false)
      },
      (title) => {
        // 响应头到达即表示后端已持久化标题；立即同步侧栏
        conversationStore.updateConversationTitleLocally(
          conversationId,
          title,
        )
      },
    )

    if (!assistantContent.trim()) {
      conversationStore.updateLastMessageContent(
        '（模型未返回内容，请稍后重试）',
      )
    }
  } catch (error) {
    console.error('AI 流式请求失败：', error)

    const tip =
      error instanceof Error
        ? error.message
        : '抱歉，AI 请求失败，请稍后重试。'

    // 若已有空的 assistant 占位，写入错误；否则追加一条
    const last = conversationStore.messages[conversationStore.messages.length - 1]
    if (last?.role === 'assistant' && !last.content) {
      conversationStore.updateLastMessageContent(`请求失败：${tip}`)
    } else if (conversationStore.currentConversationId !== null) {
      conversationStore.appendMessage(
        buildLocalMessage(
          'assistant',
          `请求失败：${tip}`,
          conversationStore.currentConversationId,
        ),
      )
    }

    ElMessage.error(tip)
  } finally {
    streaming.value = false
    await scrollToBottom(false)
  }
}

const handleExample = (text: string) => {
  void handleSend(text)
}

onMounted(async () => {
  try {
    // 1. 拉取当前用户会话列表（失败则不要继续恢复选中态）
    await conversationStore.fetchConversations()

    // 2~5. 校验持久化 ID → 恢复或默认选第一项 → 加载历史
    //     列表为空则保持未选中，不自动创建会话
    await conversationStore.restoreOrSelectDefault()

    stickToBottom.value = true
    await scrollToBottom(true)
  } catch {
    ElMessage.error(conversationStore.error || '加载会话列表失败')
    // 列表失败时清空内存中的消息展示，避免「有选中 ID、无列表/无消息」的假成功态
    conversationStore.messages = []
  }
})
</script>

<template>
  <div class="chat-workspace">
    <ChatHeader
      :conversation-title="currentTitle"
      :username="username"
      @logout="handleLogout"
    />

    <div class="chat-body">
      <ConversationSidebar
        :conversations="conversationStore.conversations"
        :current-id="conversationStore.currentConversationId"
        :loading="conversationStore.conversationsLoading"
        :deleting="conversationStore.deleting"
        @create="handleCreate"
        @select="handleSelect"
        @remove="handleRemove"
      />

      <section class="chat-main">
        <div
          ref="scrollContainer"
          class="scroll-area"
          @scroll="onScroll"
        >
          <MessagePanel
            :messages="conversationStore.messages"
            :messages-loading="conversationStore.messagesLoading"
            :streaming="streaming"
            :has-conversation="hasConversation"
            @example="handleExample"
          />
        </div>

        <ChatComposer
          v-model="draft"
          :disabled="creating"
          :streaming="streaming"
          @send="handleSend()"
        />
      </section>
    </div>
  </div>
</template>

<style scoped>
.chat-workspace {
  --chat-bg: #f4f5f7;
  --chat-surface: #ffffff;
  --chat-sidebar: #fafbfc;
  --chat-border: #e5e7eb;
  --chat-text: #111827;
  --chat-muted: #6b7280;
  --chat-accent: #0f766e;
  --chat-accent-hover: #0d9488;
  --chat-accent-soft: rgba(15, 118, 110, 0.1);

  height: 100vh;
  height: 100dvh;
  display: flex;
  flex-direction: column;
  background: var(--chat-bg);
  color: var(--chat-text);
  font-family:
    'Segoe UI',
    'PingFang SC',
    'Microsoft YaHei',
    system-ui,
    sans-serif;
  overflow: hidden;
}

.chat-body {
  flex: 1;
  min-height: 0;
  display: flex;
}

.chat-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background:
    radial-gradient(ellipse at top, rgba(15, 118, 110, 0.04), transparent 55%),
    var(--chat-bg);
}

.scroll-area {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

@media (max-width: 720px) {
  .chat-body {
    flex-direction: column;
  }

  .chat-body :deep(.sidebar) {
    width: 100%;
    max-height: 180px;
    border-right: none;
    border-bottom: 1px solid var(--chat-border);
  }
}
</style>
