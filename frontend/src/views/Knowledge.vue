<script setup lang="ts">
/**
 * 知识库页面：PDF 上传 + 文档列表 + 指定 PDF 全文总结。
 * 仅调用 src/api/knowledge.ts，JWT 由 request 拦截器处理。
 */
import { computed, onMounted, ref } from 'vue'
import axios from 'axios'
import { ElMessage } from 'element-plus'
import type {
  UploadRawFile,
  UploadRequestOptions,
} from 'element-plus'
import { useRouter } from 'vue-router'

import ChatHeader from '@/components/chat/ChatHeader.vue'
import {
  getKnowledgeDocuments,
  summarizeKnowledgeDocument,
  uploadKnowledgePdf,
  KNOWLEDGE_PDF_MAX_BYTES,
  type KnowledgeDocument,
  type SummarizeKnowledgeResult,
} from '@/api/knowledge'
import { renderMarkdown } from '@/utils/markdown'
import { useUserStore } from '@/stores/user'

const FOCUS_PLACEHOLDER =
  '总结核心知识点、重要概念和待复习内容'

const router = useRouter()
const userStore = useUserStore()

const documents = ref<KnowledgeDocument[]>([])
const listLoading = ref(false)
const listError = ref('')

const uploading = ref(false)

const selectedFilename = ref<string | null>(null)
const focus = ref('')

const summarizing = ref(false)
const summarizeError = ref('')
const summaryResult = ref<SummarizeKnowledgeResult | null>(null)

/** 递增以丢弃过期的总结响应（切换文档 / 重新发起时）。 */
let summarizeSeq = 0

const username = computed(
  () => userStore.userInfo?.username || '用户',
)

const selectedDoc = computed(() =>
  documents.value.find((item) => item.filename === selectedFilename.value) ??
  null,
)

const canSummarize = computed(() => {
  const doc = selectedDoc.value
  return (
    !!doc &&
    !doc.version_conflict &&
    !summarizing.value &&
    !listLoading.value &&
    !uploading.value
  )
})

const uploadDisabled = computed(
  () => uploading.value || summarizing.value,
)

const modeLabel = computed(() => {
  const mode = summaryResult.value?.mode
  if (mode === 'oneshot') {
    return '一次总结'
  }
  if (mode === 'map_reduce') {
    return '分批汇总（Map-Reduce）'
  }
  return mode || '—'
})

function clearSummaryState() {
  summaryResult.value = null
  summarizeError.value = ''
}

function invalidateInFlightSummarize() {
  summarizeSeq += 1
  summarizing.value = false
}

function resolveAxiosDetail(error: unknown): string | null {
  if (!axios.isAxiosError(error)) {
    return null
  }

  const data = error.response?.data as
    | { detail?: unknown; message?: unknown }
    | undefined

  if (typeof data?.detail === 'string' && data.detail.trim()) {
    return data.detail.trim()
  }

  // 少数接口可能带 message；有则使用，不强依赖
  if (typeof data?.message === 'string' && data.message.trim()) {
    return data.message.trim()
  }

  return null
}

function mapListError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (!error.response) {
      if (error.code === 'ECONNABORTED') {
        return '加载文档列表超时，请稍后重试。'
      }
      return '网络异常，无法加载文档列表，请检查网络后重试。'
    }

    const detail = resolveAxiosDetail(error)
    if (detail) {
      return detail
    }

    return `加载文档列表失败（HTTP ${error.response.status}）。`
  }

  if (error instanceof Error && error.message) {
    return error.message
  }

  return '加载文档列表失败，请稍后重试。'
}

function mapSummarizeError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (!error.response) {
      if (error.code === 'ECONNABORTED') {
        return '总结请求超时。长文档分批处理可能较慢，请稍后重试。'
      }
      return '网络异常，总结未能完成，请检查网络后重试。'
    }

    const status = error.response.status
    const detail = resolveAxiosDetail(error)

    switch (status) {
      case 400:
        return (
          detail ||
          '请求参数不合法，或文档超出处理限制。请调整后重试。'
        )
      case 404:
        return (
          detail ||
          '找不到指定文档。请刷新列表，确认文件已入库后再试。'
        )
      case 409:
        return (
          detail ||
          '文档存在版本冲突，无法可靠总结。请重新上传该 PDF 以清理冲突版本。'
        )
      case 502:
        return (
          detail ||
          'AI 总结失败（模型或分批处理出错）。请稍后重试。'
        )
      default:
        return detail || `总结失败（HTTP ${status}）。`
    }
  }

  if (error instanceof Error && error.message) {
    return error.message
  }

  return '总结失败，请稍后重试。'
}

function mapUploadError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (!error.response) {
      if (error.code === 'ECONNABORTED') {
        return '上传超时。解析与向量化可能较慢，请稍后重试。'
      }
      return '网络异常，上传未能完成，请检查网络后重试。'
    }

    const status = error.response.status
    const detail = resolveAxiosDetail(error)

    switch (status) {
      case 400:
        return detail || '上传失败：文件无效或无法解析。'
      case 413:
        return detail || 'PDF 文件不能超过 10 MB。'
      case 500:
        return detail || 'PDF 处理失败，请稍后重试。'
      default:
        return detail || `上传失败（HTTP ${status}）。`
    }
  }

  if (error instanceof Error && error.message) {
    return error.message
  }

  return '上传失败，请稍后重试。'
}

function beforeUpload(file: UploadRawFile): boolean {
  if (uploading.value) {
    ElMessage.warning('正在上传中，请稍候。')
    return false
  }

  const lowerName = file.name.toLowerCase()
  const isPdfExt = lowerName.endsWith('.pdf')
  const isPdfMime =
    !file.type ||
    file.type === 'application/pdf' ||
    file.type === 'application/x-pdf'

  if (!isPdfExt || !isPdfMime) {
    ElMessage.error('请上传 PDF 格式的文件。')
    return false
  }

  if (file.size <= 0) {
    ElMessage.error('上传的文件为空。')
    return false
  }

  if (file.size > KNOWLEDGE_PDF_MAX_BYTES) {
    ElMessage.error('PDF 文件不能超过 10 MB。')
    return false
  }

  return true
}

/**
 * 自定义上传：走 knowledge API + Axios 拦截器（JWT / 401），
 * 不使用 el-upload 默认 action，避免绕过认证。
 */
async function handleUploadRequest(options: UploadRequestOptions) {
  if (uploading.value) {
    return
  }

  uploading.value = true

  try {
    const response = await uploadKnowledgePdf(options.file as File)
    const payload = response.data
    const uploaded = payload.data

    ElMessage.success(payload.message || 'PDF 已成功导入知识库。')

    if (uploaded.stale_cleanup_ok === false) {
      ElMessage.warning(
        '文件已入库，但旧版本清理可能未完成。若出现版本冲突，请再次上传同名 PDF。',
      )
    }

    // el-upload 回调仅用于结束内部状态；业务提示与列表刷新在下方完成
    options.onSuccess?.(payload)

    await loadDocuments()

    // 选中刚上传的文档，便于立刻总结；并清空上一份总结结果
    invalidateInFlightSummarize()
    selectedFilename.value = uploaded.filename
    clearSummaryState()
  } catch (error) {
    const message = mapUploadError(error)
    ElMessage.error(message)
    options.onError?.({
      name: 'UploadError',
      message,
      status: axios.isAxiosError(error)
        ? (error.response?.status ?? 0)
        : 0,
      method: 'POST',
      url: '/api/knowledge/upload',
    })
  } finally {
    uploading.value = false
  }
}

async function loadDocuments() {
  listLoading.value = true
  listError.value = ''

  try {
    const response = await getKnowledgeDocuments()
    const data = response.data.data
    documents.value = data.documents ?? []

    // 当前选中项若已不在列表中，清空选择与总结
    if (
      selectedFilename.value &&
      !documents.value.some(
        (item) => item.filename === selectedFilename.value,
      )
    ) {
      invalidateInFlightSummarize()
      selectedFilename.value = null
      clearSummaryState()
    }
  } catch (error) {
    listError.value = mapListError(error)
    documents.value = []
  } finally {
    listLoading.value = false
  }
}

function selectDocument(doc: KnowledgeDocument) {
  if (selectedFilename.value === doc.filename) {
    return
  }

  // 切换文档时丢弃进行中的旧总结，避免回写错文档
  invalidateInFlightSummarize()
  selectedFilename.value = doc.filename
  clearSummaryState()
}

async function handleSummarize() {
  const doc = selectedDoc.value
  if (!doc || doc.version_conflict || summarizing.value) {
    return
  }

  const filename = doc.filename
  const seq = ++summarizeSeq

  summarizing.value = true
  summarizeError.value = ''
  summaryResult.value = null

  try {
    const response = await summarizeKnowledgeDocument({
      filename,
      focus: focus.value,
    })

    // 用户已切换文档或发起了更新的请求，丢弃本结果
    if (seq !== summarizeSeq || selectedFilename.value !== filename) {
      return
    }

    summaryResult.value = response.data.data
    ElMessage.success('文档总结完成')
  } catch (error) {
    if (seq !== summarizeSeq || selectedFilename.value !== filename) {
      return
    }

    summarizeError.value = mapSummarizeError(error)
    ElMessage.error(summarizeError.value)
  } finally {
    if (seq === summarizeSeq) {
      summarizing.value = false
    }
  }
}

function handleLogout() {
  userStore.logout()
  void router.push('/login')
}

onMounted(() => {
  void loadDocuments()
})
</script>

<template>
  <div class="knowledge-workspace">
    <ChatHeader
      conversation-title="我的知识库"
      :username="username"
      @logout="handleLogout"
    />

    <main class="knowledge-main">
      <header class="page-intro">
        <div>
          <h1>我的知识库</h1>
          <p>上传 PDF 到知识库，查看已入库文档，并用 AI 总结整份 PDF。</p>
        </div>
        <button
          type="button"
          class="refresh-btn"
          :disabled="listLoading || summarizing || uploading"
          @click="loadDocuments"
        >
          {{ listLoading ? '刷新中…' : '刷新列表' }}
        </button>
      </header>

      <section class="panel upload-panel">
        <h2 class="panel-title">上传 PDF</h2>
        <p class="upload-hint">
          仅支持 PDF，单文件不超过 10 MB。上传后将解析文本并写入你的知识库。
        </p>
        <el-upload
          class="pdf-uploader"
          drag
          :show-file-list="false"
          accept=".pdf,application/pdf"
          :disabled="uploadDisabled"
          :before-upload="beforeUpload"
          :http-request="handleUploadRequest"
        >
          <div class="upload-inner">
            <p class="upload-title">
              {{ uploading ? '正在上传并入库…' : '将 PDF 拖到此处，或点击选择' }}
            </p>
            <p class="upload-sub">
              {{ uploading ? '解析与向量化可能需要一些时间，请勿重复提交。' : '文件字段名 file · JWT 自动携带' }}
            </p>
          </div>
        </el-upload>
      </section>

      <div class="panels">
        <section class="panel list-panel">
          <h2 class="panel-title">文档列表</h2>

          <div v-if="listLoading" class="state-box">
            正在加载文档列表…
          </div>

          <div v-else-if="listError" class="state-box error">
            <p>{{ listError }}</p>
            <button
              type="button"
              class="retry-btn"
              @click="loadDocuments"
            >
              重试
            </button>
          </div>

          <div
            v-else-if="documents.length === 0"
            class="state-box"
          >
            暂无已入库文档。请先在上方上传 PDF。
          </div>

          <ul v-else class="doc-list">
            <li
              v-for="doc in documents"
              :key="doc.filename"
            >
              <button
                type="button"
                class="doc-card"
                :class="{
                  active: doc.filename === selectedFilename,
                  conflict: doc.version_conflict,
                }"
                @click="selectDocument(doc)"
              >
                <div class="doc-name">{{ doc.filename }}</div>
                <div class="doc-meta">
                  <span>{{ doc.page_count }} 页</span>
                  <span>{{ doc.chunk_count }} 个文本块</span>
                </div>
                <div
                  v-if="doc.version_conflict"
                  class="conflict-badge"
                >
                  版本冲突 — 请重新上传该 PDF 后再总结
                </div>
                <div
                  v-else-if="doc.file_hash"
                  class="hash-tip"
                >
                  版本：{{ doc.file_hash.slice(0, 8) }}…
                </div>
              </button>
            </li>
          </ul>
        </section>

        <section class="panel summarize-panel">
          <h2 class="panel-title">全文总结</h2>

          <div v-if="!selectedDoc" class="state-box">
            请先从左侧选择一份 PDF。
          </div>

          <template v-else>
            <div class="selected-line">
              当前文档：
              <strong>{{ selectedDoc.filename }}</strong>
            </div>

            <div
              v-if="selectedDoc.version_conflict"
              class="conflict-banner"
            >
              该文档存在版本冲突，无法直接总结。请重新上传同名 PDF
              以清理冲突版本，然后刷新列表。
            </div>

            <label class="field-label" for="focus-input">
              总结关注点（可选）
            </label>
            <textarea
              id="focus-input"
              v-model="focus"
              class="focus-input"
              rows="3"
              :placeholder="FOCUS_PLACEHOLDER"
              :disabled="summarizing || selectedDoc.version_conflict"
            />

            <div class="actions">
              <button
                type="button"
                class="summarize-btn"
                :disabled="!canSummarize"
                @click="handleSummarize"
              >
                {{ summarizing ? '正在总结…' : '开始全文总结' }}
              </button>
            </div>

            <p v-if="summarizing" class="wait-tip">
              正在读取全文并调用 AI 总结。长文档可能需要分批处理，请耐心等待，不要重复点击。
            </p>

            <div
              v-if="summarizeError"
              class="state-box error"
            >
              <p>{{ summarizeError }}</p>
              <button
                type="button"
                class="retry-btn"
                :disabled="!canSummarize"
                @click="handleSummarize"
              >
                重新总结
              </button>
            </div>

            <div
              v-if="summaryResult"
              class="result-block"
            >
              <div class="result-meta">
                <span>模式：{{ modeLabel }}</span>
                <span>批次数：{{ summaryResult.batch_count }}</span>
                <span>文本块：{{ summaryResult.chunk_count }}</span>
                <span>页数：{{ summaryResult.page_count }}</span>
                <span v-if="summaryResult.partial_count > 0">
                  局部总结：{{ summaryResult.partial_count }}
                </span>
              </div>

              <h3 class="result-title">总结结果</h3>
              <div
                class="markdown-body summary-body"
                v-html="renderMarkdown(summaryResult.summary)"
              />
            </div>
          </template>
        </section>
      </div>
    </main>
  </div>
</template>

<style scoped>
.knowledge-workspace {
  --chat-bg: #f4f5f7;
  --chat-surface: #ffffff;
  --chat-sidebar: #fafbfc;
  --chat-border: #e5e7eb;
  --chat-text: #111827;
  --chat-muted: #6b7280;
  --chat-accent: #0f766e;
  --chat-accent-hover: #0d9488;
  --chat-accent-soft: rgba(15, 118, 110, 0.1);

  min-height: 100vh;
  min-height: 100dvh;
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
}

.knowledge-main {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 24px 20px 40px;
  box-sizing: border-box;
  background:
    radial-gradient(ellipse at top, rgba(15, 118, 110, 0.04), transparent 55%),
    var(--chat-bg);
}

.page-intro {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  max-width: 1100px;
  margin: 0 auto 20px;
}

.page-intro h1 {
  margin: 0 0 8px;
  font-size: 28px;
  font-weight: 600;
  color: var(--chat-text);
  letter-spacing: -0.02em;
}

.page-intro p {
  margin: 0;
  color: var(--chat-muted);
  font-size: 14px;
}

.upload-panel {
  max-width: 1100px;
  margin: 0 auto 16px;
}

.upload-hint {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--chat-muted);
  line-height: 1.5;
}

.pdf-uploader {
  width: 100%;
}

.pdf-uploader :deep(.el-upload) {
  width: 100%;
}

.pdf-uploader :deep(.el-upload-dragger) {
  width: 100%;
  padding: 28px 16px;
  border-radius: 10px;
  border-color: var(--chat-border);
  background: #fafbfc;
}

.pdf-uploader :deep(.el-upload-dragger:hover) {
  border-color: var(--chat-accent);
}

.upload-inner {
  pointer-events: none;
}

.upload-title {
  margin: 0 0 6px;
  font-size: 15px;
  font-weight: 600;
  color: var(--chat-text);
}

.upload-sub {
  margin: 0;
  font-size: 12px;
  color: var(--chat-muted);
}

.refresh-btn,
.retry-btn,
.summarize-btn {
  border: none;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  transition: background 0.15s ease, opacity 0.15s ease;
}

.refresh-btn {
  flex-shrink: 0;
  padding: 8px 14px;
  border: 1px solid var(--chat-border);
  background: var(--chat-surface);
  color: var(--chat-text);
}

.refresh-btn:hover:not(:disabled) {
  border-color: #c5cad3;
  background: #f3f4f6;
}

.refresh-btn:disabled,
.summarize-btn:disabled,
.retry-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.panels {
  display: grid;
  grid-template-columns: minmax(260px, 360px) minmax(0, 1fr);
  gap: 16px;
  max-width: 1100px;
  margin: 0 auto;
  align-items: start;
}

.panel {
  background: var(--chat-surface);
  border: 1px solid var(--chat-border);
  border-radius: 12px;
  padding: 16px;
  box-sizing: border-box;
}

.panel-title {
  margin: 0 0 14px;
  font-size: 15px;
  font-weight: 600;
}

.state-box {
  padding: 16px;
  border-radius: 8px;
  background: var(--chat-sidebar);
  color: var(--chat-muted);
  font-size: 14px;
  line-height: 1.5;
}

.state-box.error {
  background: #fef2f2;
  color: #991b1b;
}

.state-box .retry-btn {
  margin-top: 10px;
  padding: 6px 12px;
  background: var(--chat-accent);
  color: #fff;
}

.state-box .retry-btn:hover:not(:disabled) {
  background: var(--chat-accent-hover);
}

.doc-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: calc(100vh - 220px);
  overflow-y: auto;
}

.doc-card {
  width: 100%;
  text-align: left;
  border: 1px solid var(--chat-border);
  background: #fff;
  border-radius: 10px;
  padding: 12px;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.doc-card:hover {
  border-color: #c5cad3;
}

.doc-card.active {
  border-color: var(--chat-accent);
  background: var(--chat-accent-soft);
}

.doc-card.conflict {
  border-color: #f59e0b;
}

.doc-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--chat-text);
  word-break: break-all;
}

.doc-meta {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 12px;
  color: var(--chat-muted);
}

.conflict-badge {
  margin-top: 8px;
  font-size: 12px;
  color: #b45309;
  font-weight: 500;
}

.hash-tip {
  margin-top: 6px;
  font-size: 11px;
  color: var(--chat-muted);
  font-family: ui-monospace, Consolas, monospace;
}

.selected-line {
  margin-bottom: 12px;
  font-size: 14px;
  color: var(--chat-muted);
}

.selected-line strong {
  color: var(--chat-text);
}

.conflict-banner {
  margin-bottom: 14px;
  padding: 10px 12px;
  border-radius: 8px;
  background: #fffbeb;
  border: 1px solid #fcd34d;
  color: #92400e;
  font-size: 13px;
  line-height: 1.5;
}

.field-label {
  display: block;
  margin-bottom: 6px;
  font-size: 13px;
  color: var(--chat-muted);
}

.focus-input {
  width: 100%;
  box-sizing: border-box;
  resize: vertical;
  min-height: 72px;
  padding: 10px 12px;
  border: 1px solid var(--chat-border);
  border-radius: 8px;
  font: inherit;
  font-size: 14px;
  color: var(--chat-text);
  background: #fff;
}

.focus-input:focus {
  outline: 2px solid var(--chat-accent-soft);
  border-color: var(--chat-accent);
}

.actions {
  margin-top: 12px;
}

.summarize-btn {
  padding: 10px 18px;
  background: var(--chat-accent);
  color: #fff;
  font-weight: 500;
}

.summarize-btn:hover:not(:disabled) {
  background: var(--chat-accent-hover);
}

.wait-tip {
  margin: 12px 0 0;
  font-size: 13px;
  color: var(--chat-muted);
  line-height: 1.5;
}

.result-block {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--chat-border);
}

.result-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 14px;
  margin-bottom: 12px;
  font-size: 12px;
  color: var(--chat-muted);
}

.result-title {
  margin: 0 0 10px;
  font-size: 15px;
  font-weight: 600;
}

.summary-body {
  padding: 14px;
  border-radius: 10px;
  border: 1px solid var(--chat-border);
  background: #fafbfc;
  font-size: 14px;
  line-height: 1.65;
  color: var(--chat-text);
  overflow-x: auto;
}

.summary-body :deep(pre.md-code-block) {
  overflow-x: auto;
  padding: 12px;
  border-radius: 8px;
  background: #111827;
  color: #f9fafb;
}

.summary-body :deep(code) {
  font-family: ui-monospace, Consolas, monospace;
  font-size: 0.92em;
}

.summary-body :deep(p) {
  margin: 0 0 0.75em;
}

.summary-body :deep(p:last-child) {
  margin-bottom: 0;
}

@media (max-width: 860px) {
  .panels {
    grid-template-columns: 1fr;
  }

  .doc-list {
    max-height: 280px;
  }

  .page-intro h1 {
    font-size: 22px;
  }
}
</style>
