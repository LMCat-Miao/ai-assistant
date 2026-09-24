<script setup lang="ts">
/**
 * 底部输入区：多行输入、Enter 发送、Shift+Enter 换行。
 */
import { computed } from 'vue'

const props = defineProps<{
  modelValue: string
  disabled: boolean
  streaming: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  send: []
}>()

const canSend = computed(
  () => props.modelValue.trim().length > 0 && !props.disabled && !props.streaming,
)

const onKeydown = (event: KeyboardEvent) => {
  // Enter 发送；Shift+Enter 换行（浏览器默认插入换行）
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    if (canSend.value) {
      emit('send')
    }
  }
}
</script>

<template>
  <footer class="composer">
    <div class="composer-inner">
      <textarea
        :value="modelValue"
        class="composer-input"
        rows="1"
        placeholder="输入你的问题…（Enter 发送，Shift + Enter 换行）"
        :disabled="disabled || streaming"
        @input="emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
        @keydown="onKeydown"
      />
      <button
        type="button"
        class="send-btn"
        :disabled="!canSend"
        @click="emit('send')"
      >
        {{ streaming ? '生成中…' : '发送' }}
      </button>
    </div>
  </footer>
</template>

<style scoped>
.composer {
  flex-shrink: 0;
  padding: 12px 20px 20px;
  background: linear-gradient(to top, var(--chat-bg) 70%, transparent);
}

.composer-inner {
  max-width: 820px;
  margin: 0 auto;
  display: flex;
  gap: 10px;
  align-items: flex-end;
  padding: 10px 12px;
  border: 1px solid var(--chat-border);
  border-radius: 16px;
  background: var(--chat-surface);
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
}

.composer-input {
  flex: 1;
  min-height: 44px;
  max-height: 160px;
  resize: vertical;
  border: none;
  outline: none;
  background: transparent;
  font: inherit;
  font-size: 14px;
  line-height: 1.5;
  color: var(--chat-text);
  padding: 8px 4px;
}

.composer-input:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.send-btn {
  flex-shrink: 0;
  border: none;
  border-radius: 10px;
  padding: 10px 16px;
  background: var(--chat-accent);
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s ease, opacity 0.15s ease;
}

.send-btn:hover:not(:disabled) {
  background: var(--chat-accent-hover);
}

.send-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
</style>
