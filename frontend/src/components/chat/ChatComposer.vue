<script setup lang="ts">
/**
 * 底部输入区：知识库开关、可选文档、多行输入、Enter 发送。
 */
import { computed } from 'vue'
import type { KnowledgeDocument } from '@/api/knowledge'

const props = defineProps<{
  modelValue: string
  disabled: boolean
  streaming: boolean
  useKnowledge: boolean
  knowledgeFilename: string
  documents: KnowledgeDocument[]
  documentsLoading: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'update:useKnowledge': [value: boolean]
  'update:knowledgeFilename': [value: string]
  send: []
}>()

const canSend = computed(
  () => props.modelValue.trim().length > 0 && !props.disabled && !props.streaming,
)

/** 可选文档：排除版本冲突，避免误选无法可靠检索的文件 */
const selectableDocuments = computed(() =>
  props.documents.filter((item) => !item.version_conflict),
)

const hasConflictOnly = computed(
  () =>
    props.documents.length > 0 && selectableDocuments.value.length === 0,
)

const emptyKnowledgeTip = computed(() => {
  if (!props.useKnowledge) {
    return ''
  }
  if (props.documentsLoading) {
    return '正在加载知识库文档…'
  }
  if (props.documents.length === 0) {
    return '当前知识库暂无可用文档。请先到「知识库」上传 PDF，否则无法引用资料。'
  }
  if (hasConflictOnly.value) {
    return '知识库文档均存在版本冲突，请先重新上传清理后再启用检索。'
  }
  return ''
})

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
    <div class="composer-panel">
      <div class="knowledge-bar">
        <label class="toggle-row">
          <input
            type="checkbox"
            class="toggle-input"
            :checked="useKnowledge"
            :disabled="disabled || streaming"
            @change="
              emit(
                'update:useKnowledge',
                ($event.target as HTMLInputElement).checked,
              )
            "
          >
          <span class="toggle-label">启用知识库</span>
        </label>

        <select
          v-if="useKnowledge"
          class="doc-select"
          :value="knowledgeFilename"
          :disabled="disabled || streaming || documentsLoading"
          @change="
            emit(
              'update:knowledgeFilename',
              ($event.target as HTMLSelectElement).value,
            )
          "
        >
          <option value="">
            全部已入库文档
          </option>
          <option
            v-for="doc in selectableDocuments"
            :key="doc.filename"
            :value="doc.filename"
          >
            {{ doc.filename }}（{{ doc.page_count }} 页）
          </option>
        </select>
      </div>

      <p
        v-if="emptyKnowledgeTip"
        class="knowledge-tip"
        role="status"
      >
        {{ emptyKnowledgeTip }}
      </p>

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
    </div>
  </footer>
</template>

<style scoped>
.composer {
  flex-shrink: 0;
  padding: 12px 20px 20px;
  background: linear-gradient(to top, var(--chat-bg) 70%, transparent);
}

.composer-panel {
  max-width: 820px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.knowledge-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 14px;
  padding: 0 4px;
}

.toggle-row {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;
  font-size: 13px;
  color: var(--chat-text);
}

.toggle-input {
  width: 14px;
  height: 14px;
  accent-color: var(--chat-accent);
  cursor: pointer;
}

.toggle-input:disabled {
  cursor: not-allowed;
}

.toggle-label {
  font-weight: 500;
}

.doc-select {
  min-width: 180px;
  max-width: 100%;
  flex: 1;
  padding: 6px 10px;
  border: 1px solid var(--chat-border);
  border-radius: 8px;
  background: var(--chat-surface);
  color: var(--chat-text);
  font: inherit;
  font-size: 13px;
}

.doc-select:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.knowledge-tip {
  margin: 0;
  padding: 8px 10px;
  border-radius: 8px;
  background: #fffbeb;
  border: 1px solid #fcd34d;
  color: #92400e;
  font-size: 12px;
  line-height: 1.45;
}

.composer-inner {
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
