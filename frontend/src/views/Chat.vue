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
import {
  getKnowledgeDocuments,
  type KnowledgeDocument,
} from '@/api/knowledge'
import type { Message } from '@/api/message'
import { useConversationStore } from '@/stores/conversation'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()
const conversationStore = useConversationStore()

const draft = ref('')
const streaming = ref(false)
const creating = ref(false)

/** 知识库开关默认关闭，保持原有普通聊天行为 */
const useKnowledge = ref(false)
const knowledgeFilename = ref('')
const knowledgeDocuments = ref<KnowledgeDocument[]>([])
const knowledgeDocumentsLoading = ref(false)

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
  // logout 内同步清空会话内存 + Local Storage，再跳转
  userStore.logout()
  router.push('/login')
}

const handleCreate = async () => {
  if (creating.value) {
    return
  }

  if (streaming.value || conversationStore.interactionLocked) {
    ElMessage.warning('请等待当前回答生成完成后再新建会话')
    return
  }

  creating.value = true

  try {
    await conversationStore.createNewConversation()
    stickToBottom.value = true
    await scrollToBottom(true)
    ElMessage.success('已创建新对话')
  } catch (error) {
    ElMessage.error(
      error instanceof Error
        ? error.message
        : conversationStore.error || '创建会话失败',
    )
  } finally {
    creating.value = false
  }
}

const handleSelect = async (id: number) => {
  if (streaming.value || conversationStore.interactionLocked) {
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
  } catch (error) {
    ElMessage.error(
      error instanceof Error
        ? error.message
        : conversationStore.error || '切换会话失败',
    )
  }
}

const handleRemove = async (id: number) => {
  if (conversationStore.deleting) {
    return
  }

  if (streaming.value || conversationStore.interactionLocked) {
    ElMessage.warning('请等待当前回答生成完成后再删除会话')
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

const loadKnowledgeDocuments = async () => {
  knowledgeDocumentsLoading.value = true
  try {
    const response = await getKnowledgeDocuments()
    knowledgeDocuments.value = response.data.data.documents ?? []

    // 若当前选中的文件已不在可选列表中，清空选择
    const stillValid = knowledgeDocuments.value.some(
      (item) =>
        item.filename === knowledgeFilename.value && !item.version_conflict,
    )
    if (knowledgeFilename.value && !stillValid) {
      knowledgeFilename.value = ''
    }
  } catch {
    knowledgeDocuments.value = []
    // 不阻断聊天；开启知识库时 Composer 会提示无文档
  } finally {
    knowledgeDocumentsLoading.value = false
  }
}

/**
 * 发送消息：
 * 1. 若无当前会话则先创建
 * 2. 本地追加 user / assistant 占位
 * 3. 将发送瞬间的 use_knowledge / knowledge_filename 固定进本次请求
 */
const handleSend = async (preset?: string) => {
  const text = (preset ?? draft.value).trim()

  // 生成中禁止再次发送，避免并行多个流式请求
  if (!text || streaming.value || conversationStore.interactionLocked) {
    return
  }

  // 固定本次请求参数，避免发送后切换开关影响进行中的请求
  const requestUseKnowledge = useKnowledge.value === true
  const requestKnowledgeFilename = knowledgeFilename.value.trim()

  if (requestUseKnowledge && knowledgeDocuments.value.length === 0) {
    ElMessage.warning(
      '已启用知识库，但当前没有可用文档。请先到「知识库」上传 PDF，或关闭开关后再发送。',
    )
  }

  draft.value = ''
  stickToBottom.value = true

  // 捕获发送时的世代；退出登录后回调不得再写 Store
  const generationAtSend = conversationStore.sessionGeneration

  try {
    // 先确保会话存在，再进入 streaming 锁定，避免「生成中新建」与锁冲突
    let conversationId = conversationStore.currentConversationId

    if (conversationId === null) {
      creating.value = true
      try {
        const created = await conversationStore.createNewConversation()
        conversationId = created.id
      } finally {
        creating.value = false
      }
    }

    streaming.value = true
    conversationStore.setInteractionLocked(true)

    conversationStore.appendMessage(
      buildLocalMessage('user', text, conversationId),
    )
    await scrollToBottom(true)

    conversationStore.appendMessage(
      buildLocalMessage('assistant', '', conversationId),
    )

    let assistantContent = ''

    await streamChat({
      conversationId,
      message: text,
      token: userStore.token,
      useKnowledge: requestUseKnowledge,
      knowledgeFilename: requestKnowledgeFilename || null,
      onChunk: async (chunk) => {
        if (conversationStore.sessionGeneration !== generationAtSend) {
          return
        }
        assistantContent += chunk
        conversationStore.updateLastMessageContent(assistantContent)
        await scrollToBottom(false)
      },
      onTitle: (title) => {
        if (conversationStore.sessionGeneration !== generationAtSend) {
          return
        }
        conversationStore.updateConversationTitleLocally(
          conversationId,
          title,
        )
      },
      onCitations: (citations, status) => {
        if (conversationStore.sessionGeneration !== generationAtSend) {
          return
        }
        conversationStore.updateLastMessageCitations(citations, status)
      },
    })

    if (conversationStore.sessionGeneration !== generationAtSend) {
      return
    }

    if (!assistantContent.trim()) {
      conversationStore.updateLastMessageContent(
        '（模型未返回内容，请稍后重试）',
      )
    }
  } catch (error) {
    if (conversationStore.sessionGeneration !== generationAtSend) {
      return
    }

    console.error('AI 流式请求失败：', error)

    const tip =
      error instanceof Error
        ? error.message
        : '抱歉，AI 请求失败，请稍后重试。'

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
    // 正常结束或异常后都必须解锁，恢复切换/新建/发送
    streaming.value = false
    conversationStore.setInteractionLocked(false)
    if (conversationStore.sessionGeneration === generationAtSend) {
      await scrollToBottom(false)
    }
  }
}

const handleExample = (text: string) => {
  void handleSend(text)
}

onMounted(async () => {
  // 文档列表与会话列表并行加载；失败不阻断聊天
  void loadKnowledgeDocuments()

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
        :locked="streaming || conversationStore.interactionLocked"
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
          v-model:use-knowledge="useKnowledge"
          v-model:knowledge-filename="knowledgeFilename"
          :disabled="creating"
          :streaming="streaming"
          :documents="knowledgeDocuments"
          :documents-loading="knowledgeDocumentsLoading"
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
