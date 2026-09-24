<script setup lang="ts">
/**
 * 左侧会话栏：新建、列表、选中高亮、删除入口。
 * 数据全部来自 conversation Store，无假数据。
 */
import type { Conversation } from '@/api/conversation'

defineProps<{
  conversations: Conversation[]
  currentId: number | null
  loading: boolean
  deleting?: boolean
}>()

const emit = defineEmits<{
  create: []
  select: [id: number]
  remove: [id: number]
}>()
</script>

<template>
  <aside class="sidebar">
    <button
      type="button"
      class="new-chat-btn"
      @click="emit('create')"
    >
      + 新建对话
    </button>

    <div class="list-label">历史会话</div>

    <div v-if="loading" class="state-tip">加载中…</div>

    <div
      v-else-if="conversations.length === 0"
      class="state-tip"
    >
      还没有会话，点击上方新建一次对话吧。
    </div>

    <ul v-else class="conversation-list">
      <li
        v-for="item in conversations"
        :key="item.id"
        class="conversation-item"
        :class="{ active: item.id === currentId }"
      >
        <button
          type="button"
          class="conversation-main"
          @click="emit('select', item.id)"
        >
          <span class="conversation-title">{{ item.title || '新会话' }}</span>
        </button>

        <button
          type="button"
          class="delete-btn"
          title="删除会话"
          :disabled="deleting"
          @click.stop="emit('remove', item.id)"
        >
          删除
        </button>
      </li>
    </ul>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 260px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px 12px;
  border-right: 1px solid var(--chat-border);
  background: var(--chat-sidebar);
  min-height: 0;
  overflow: hidden;
}

.new-chat-btn {
  width: 100%;
  border: none;
  border-radius: 10px;
  padding: 10px 12px;
  background: var(--chat-accent);
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s ease, transform 0.15s ease;
}

.new-chat-btn:hover {
  background: var(--chat-accent-hover);
}

.new-chat-btn:active {
  transform: scale(0.98);
}

.list-label {
  font-size: 12px;
  color: var(--chat-muted);
  padding: 0 6px;
}

.state-tip {
  font-size: 13px;
  color: var(--chat-muted);
  line-height: 1.5;
  padding: 8px 6px;
}

.conversation-list {
  list-style: none;
  margin: 0;
  padding: 0;
  overflow-y: auto;
  min-height: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.conversation-item {
  display: flex;
  align-items: center;
  gap: 4px;
  border-radius: 10px;
  transition: background 0.15s ease;
}

.conversation-item:hover {
  background: rgba(15, 118, 110, 0.06);
}

.conversation-item.active {
  background: var(--chat-accent-soft);
}

.conversation-main {
  flex: 1;
  min-width: 0;
  border: none;
  background: transparent;
  text-align: left;
  padding: 10px 8px 10px 10px;
  cursor: pointer;
  color: var(--chat-text);
}

.conversation-title {
  display: block;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.delete-btn {
  border: none;
  background: transparent;
  color: var(--chat-muted);
  font-size: 12px;
  padding: 6px 8px;
  margin-right: 4px;
  border-radius: 6px;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s ease, color 0.15s ease, background 0.15s ease;
}

.conversation-item:hover .delete-btn,
.conversation-item.active .delete-btn {
  opacity: 1;
}

.delete-btn:hover {
  color: #b91c1c;
  background: rgba(185, 28, 28, 0.08);
}

.delete-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

@media (max-width: 860px) {
  .sidebar {
    width: 220px;
  }
}
</style>
