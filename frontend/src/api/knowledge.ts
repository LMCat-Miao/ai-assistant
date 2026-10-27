/**
 * 知识库 API。
 *
 * 复用 `@/utils/request` 的 Axios 实例（Base URL、JWT、401 处理）。
 *
 * 注意：当前后端知识库接口返回结构为 { message, data }，
 * 不含 conversations / auth 中的 code 字段，类型需与此对齐。
 */

import request from '@/utils/request'

/**
 * 知识库接口统一包装（以 knowledge.py 实际返回为准）。
 */
export interface KnowledgeApiResponse<T> {
  message: string
  data: T
}

/**
 * 单条知识库文档信息（GET /api/knowledge/documents）。
 */
export interface KnowledgeDocument {
  filename: string
  chunk_count: number
  page_count: number
  /** 可唯一确定版本时有值；版本冲突时为 null */
  file_hash: string | null
  /** 同名多版本或新旧混杂时为 true */
  version_conflict: boolean
}

/**
 * 文档列表的 data 字段。
 */
export interface KnowledgeDocumentsData {
  count: number
  documents: KnowledgeDocument[]
}

/**
 * 全文总结请求体。
 * focus 可选；未填写时不要传空字符串。
 */
export interface SummarizeKnowledgeRequest {
  filename: string
  focus?: string
}

/**
 * 全文总结成功时的 data 字段。
 */
export interface SummarizeKnowledgeResult {
  filename: string
  file_hash: string | null
  chunk_count: number
  page_count: number
  batch_count: number
  mode: 'oneshot' | 'map_reduce'
  partial_count: number
  summary: string
}

/**
 * PDF 上传成功时的 data 字段（与 ingest_pdf 返回一致）。
 */
export interface UploadKnowledgeResult {
  filename: string
  file_hash: string
  pages: number
  chunks: number
  removed_old_chunks: number
  stale_cleanup_ok: boolean
  stale_cleanup_error: string | null
}

/** 与后端 MAX_FILE_SIZE 一致：10 MB。 */
export const KNOWLEDGE_PDF_MAX_BYTES = 10 * 1024 * 1024

/** Map-Reduce / 入库向量化可能较慢，单独放宽超时，避免沿用全局 10s。 */
const SUMMARIZE_TIMEOUT_MS = 180_000
const UPLOAD_TIMEOUT_MS = 180_000

/**
 * 获取当前登录用户的知识库文档列表。
 *
 * 实际路径：GET /api/knowledge/documents
 * JWT：由 request 拦截器从 userStore.token 自动附加。
 */
export function getKnowledgeDocuments() {
  return request.get<KnowledgeApiResponse<KnowledgeDocumentsData>>(
    '/api/knowledge/documents',
  )
}

/**
 * 上传 PDF 到当前用户知识库。
 *
 * 实际路径：POST /api/knowledge/upload
 * 表单字段名：file（multipart/form-data）
 * JWT：由 request 拦截器自动附加，勿硬编码 token。
 *
 * 注意：不要手动写死 Content-Type，以便 Axios 带上正确的 multipart boundary。
 */
export function uploadKnowledgePdf(file: File) {
  const formData = new FormData()
  formData.append('file', file)

  return request.post<KnowledgeApiResponse<UploadKnowledgeResult>>(
    '/api/knowledge/upload',
    formData,
    {
      timeout: UPLOAD_TIMEOUT_MS,
    },
  )
}

/**
 * 对当前用户指定 PDF 做全文总结。
 *
 * 实际路径：POST /api/knowledge/summarize
 *
 * 错误状态码（由调用方按需处理，拦截器仅统一处理 401）：
 * - 400 参数错误或文档过长
 * - 404 文档不存在
 * - 409 版本冲突
 * - 502 模型调用或分批失败
 */
export function summarizeKnowledgeDocument(
  payload: SummarizeKnowledgeRequest,
) {
  const filename = payload.filename.trim()
  const body: { filename: string; focus?: string } = {
    filename,
  }

  const focus = payload.focus?.trim()
  if (focus) {
    body.focus = focus
  }

  return request.post<KnowledgeApiResponse<SummarizeKnowledgeResult>>(
    '/api/knowledge/summarize',
    body,
    {
      timeout: SUMMARIZE_TIMEOUT_MS,
    },
  )
}
