<script setup lang="ts">
/**
 * 主聊天区：消息列表、欢迎页、Markdown 渲染、生成中提示。
 */
import { renderMarkdown } from '@/utils/markdown'
import type { Message } from '@/api/message'

defineProps<{
  messages: Message[]
  messagesLoading: boolean
  streaming: boolean
  hasConversation: boolean
}>()

const emit = defineEmits<{
  example: [text: string]
}>()

const examples = [
  '请用通俗例子解释 JavaScript 闭包',
  'Vue3 Composition API 和 Options API 怎么选？',
  '帮我梳理一次 HTTP 请求从浏览器到服务器的路径',
]
</script>

<template>
  <div class="message-panel">
    <div v-if="messagesLoading" class="panel-state">正在加载历史消息…</div>

    <template v-else-if="!hasConversation">
      <div class="welcome">
        <h2>开始一段新的学习对话</h2>
        <p>先在左侧新建对话，或直接在下方输入问题（会自动创建会话）。</p>
      </div>
    </template>

    <template v-else-if="messages.length === 0">
      <div class="welcome">
        <h2>你好，我是你的 AI 学习助手</h2>
        <p>可以问概念、让我拆解代码，或一步步带你做练习。</p>
        <div class="examples">
          <button
            v-for="item in examples"
            :key="item"
            type="button"
            class="example-chip"
            @click="emit('example', item)"
          >
            {{ item }}
          </button>
        </div>
      </div>
    </template>

    <div v-else class="message-list">
      <article
        v-for="item in messages"
        :key="item.id"
        class="message-row"
        :class="item.role"
      >
        <div class="role-label">
          {{ item.role === 'user' ? '我' : '助手' }}
        </div>
        <div
          class="bubble"
          :class="item.role"
        >
          <div
            v-if="item.role === 'assistant'"
            class="markdown-body"
            v-html="renderMarkdown(item.content)"
          />
          <div v-else class="plain-text">{{ item.content }}</div>
        </div>
      </article>

      <div v-if="streaming" class="streaming-tip">
        <span class="dot" />
        正在生成回答…
      </div>
    </div>
  </div>
</template>

<style scoped>
.message-panel {
  padding: 24px 20px 12px;
  min-height: 100%;
  box-sizing: border-box;
}

.panel-state,
.welcome {
  max-width: 720px;
  margin: 48px auto 0;
  text-align: center;
  color: var(--chat-muted);
}

.welcome h2 {
  margin: 0 0 8px;
  font-size: 22px;
  font-weight: 600;
  color: var(--chat-text);
  letter-spacing: -0.02em;
}

.welcome p {
  margin: 0 auto 20px;
  max-width: 420px;
  font-size: 14px;
  line-height: 1.6;
}

.examples {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
}

.example-chip {
  border: 1px solid var(--chat-border);
  background: var(--chat-surface);
  color: var(--chat-text);
  border-radius: 999px;
  padding: 8px 14px;
  font-size: 13px;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.example-chip:hover {
  border-color: var(--chat-accent);
  background: var(--chat-accent-soft);
}

.message-list {
  max-width: 820px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.message-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
  animation: fade-in 0.18s ease;
}

.message-row.user {
  align-items: flex-end;
}

.message-row.assistant {
  align-items: flex-start;
}

.role-label {
  font-size: 12px;
  color: var(--chat-muted);
  padding: 0 4px;
}

.bubble {
  max-width: min(100%, 680px);
  border-radius: 14px;
  padding: 12px 14px;
  font-size: 14px;
  line-height: 1.65;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.bubble.user {
  background: var(--chat-accent);
  color: #fff;
  border-bottom-right-radius: 4px;
}

.bubble.assistant {
  background: var(--chat-surface);
  color: var(--chat-text);
  border: 1px solid var(--chat-border);
  border-bottom-left-radius: 4px;
}

.plain-text {
  white-space: pre-wrap;
}

.markdown-body :deep(p) {
  margin: 0 0 0.75em;
}

.markdown-body :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 0 0 0.75em;
  padding-left: 1.25em;
}

.markdown-body :deep(pre.md-code-block) {
  margin: 0.75em 0;
  padding: 12px 14px;
  border-radius: 10px;
  background: #0f172a;
  color: #e2e8f0;
  overflow-x: auto;
  font-size: 13px;
  line-height: 1.55;
  position: relative;
}

.markdown-body :deep(pre.md-code-block[data-lang])::before {
  content: attr(data-lang);
  display: block;
  font-size: 11px;
  color: #94a3b8;
  margin-bottom: 8px;
  text-transform: lowercase;
}

.markdown-body :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.92em;
  display: inline;
  padding: 0;
  background: transparent;
  color: inherit;
  border-radius: 0;
  line-height: inherit;
}

.markdown-body :deep(:not(pre) > code) {
  display: inline;
  background: #f1f5f9;
  color: #0f766e;
  padding: 0.1em 0.35em;
  border-radius: 4px;
}

.markdown-body :deep(pre code) {
  display: block;
  background: transparent;
  color: inherit;
  padding: 0;
  white-space: pre;
}

.streaming-tip {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--chat-muted);
  padding-left: 4px;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--chat-accent);
  animation: pulse 1s ease infinite;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 0.35;
    transform: scale(0.9);
  }
  50% {
    opacity: 1;
    transform: scale(1);
  }
}

@keyframes fade-in {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
