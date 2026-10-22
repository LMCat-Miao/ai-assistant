"""指定 PDF 的全文 Map-Reduce 总结服务。"""

from __future__ import annotations

from typing import Any, Callable

from app.rag.vector_store import VectorStore
from app.services.ai_service import chat_with_ai
from app.services.rag_document_service import (
    DocumentNotFoundError,
    DocumentVersionConflictError,
    get_document_chunks,
)


# 单批送入模型的正文最大字符数（不含提示词包装）。
MAX_BATCH_CHARS = 6000

# 防止超长文档无限调用模型。
MAX_BATCHES = 20

# 单次模型调用超时（秒）。
LLM_CALL_TIMEOUT_SECONDS = 60


class DocumentTooLargeError(Exception):
    """文档分批后超过允许的最大批次数。"""


class SummarizeModelError(Exception):
    """模型调用失败或某批次失败；不得返回声称完整的终稿。"""


ChatFn = Callable[..., str]


def _format_chunk_block(chunk: dict[str, Any]) -> str:
    page = chunk.get("page")
    page_label = f"第 {page} 页" if page is not None else "页码未知"
    index = chunk.get("chunk_index")
    return (
        f"[Chunk {index} | {page_label}]\n"
        f"{chunk.get('content') or ''}"
    )


def split_chunks_into_batches(
    chunks: list[dict[str, Any]],
    max_batch_chars: int = MAX_BATCH_CHARS,
) -> list[list[dict[str, Any]]]:
    """按字符预算把有序 Chunk 分成连续批次，保持文档顺序。"""

    if max_batch_chars < 1:
        raise ValueError("max_batch_chars 必须大于等于 1")

    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0

    for chunk in chunks:
        block = _format_chunk_block(chunk)
        block_len = len(block)

        # 单个 Chunk 超长时单独成批，避免死循环。
        if current and current_chars + block_len + 2 > max_batch_chars:
            batches.append(current)
            current = []
            current_chars = 0

        current.append(chunk)
        current_chars += block_len + (2 if current_chars else 0)

        if current_chars >= max_batch_chars:
            batches.append(current)
            current = []
            current_chars = 0

    if current:
        batches.append(current)

    return batches


def _batch_text(batch: list[dict[str, Any]]) -> str:
    return "\n\n".join(_format_chunk_block(chunk) for chunk in batch)


def _call_model(
    messages: list[dict[str, str]],
    *,
    chat_fn: ChatFn,
    timeout: float,
    error_prefix: str,
) -> str:
    try:
        text = chat_fn(messages, timeout=timeout)
    except Exception as exc:
        raise SummarizeModelError(
            f"{error_prefix}：模型调用失败（{exc}）。未生成完整终稿。"
        ) from exc

    if not (text or "").strip():
        raise SummarizeModelError(
            f"{error_prefix}：模型返回空内容。未生成完整终稿。"
        )

    return text.strip()


def _map_batch_summary(
    *,
    filename: str,
    batch_index: int,
    batch_count: int,
    batch: list[dict[str, Any]],
    focus: str | None,
    chat_fn: ChatFn,
    timeout: float,
) -> str:
    focus_line = (
        f"用户补充要求：{focus.strip()}\n"
        if focus and focus.strip()
        else ""
    )
    system = (
        "你是文档总结助手。请仅根据给定的文档片段做阶段性总结，"
        "不要编造片段中不存在的信息，不要声称已覆盖全文。"
    )
    user = (
        f"文件名：{filename}\n"
        f"这是全文的第 {batch_index}/{batch_count} 批片段。\n"
        f"{focus_line}"
        "请输出该批次的要点总结，保留关键事实、结构与页码线索。\n\n"
        f"{_batch_text(batch)}"
    )
    return _call_model(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        chat_fn=chat_fn,
        timeout=timeout,
        error_prefix=f"第 {batch_index}/{batch_count} 批总结失败",
    )


def _reduce_summaries(
    *,
    filename: str,
    partials: list[str],
    focus: str | None,
    chat_fn: ChatFn,
    timeout: float,
) -> str:
    focus_line = (
        f"用户补充要求：{focus.strip()}\n"
        if focus and focus.strip()
        else ""
    )
    numbered = "\n\n".join(
        f"[局部总结 {index}]\n{text}"
        for index, text in enumerate(partials, start=1)
    )
    system = (
        "你是文档总结助手。请把多段局部总结合并为一份完整、有结构的终稿。"
        "不要编造局部总结中没有的信息。"
    )
    user = (
        f"文件名：{filename}\n"
        f"{focus_line}"
        "以下是按文档顺序得到的局部总结，请合并为最终全文总结。\n\n"
        f"{numbered}"
    )
    return _call_model(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        chat_fn=chat_fn,
        timeout=timeout,
        error_prefix="汇总各批次结果失败",
    )


def _oneshot_summary(
    *,
    filename: str,
    batch: list[dict[str, Any]],
    focus: str | None,
    chat_fn: ChatFn,
    timeout: float,
) -> str:
    focus_line = (
        f"用户补充要求：{focus.strip()}\n"
        if focus and focus.strip()
        else ""
    )
    system = (
        "你是文档总结助手。请根据提供的全文内容写出结构清晰的总结，"
        "不要编造原文没有的信息。"
    )
    user = (
        f"文件名：{filename}\n"
        f"{focus_line}"
        "以下是按页码与文档顺序排列的全文内容，请输出完整总结。\n\n"
        f"{_batch_text(batch)}"
    )
    return _call_model(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        chat_fn=chat_fn,
        timeout=timeout,
        error_prefix="全文总结失败",
    )


def summarize_document(
    user_id: str,
    filename: str,
    focus: str | None = None,
    store: VectorStore | None = None,
    *,
    chat_fn: ChatFn | None = None,
    max_batch_chars: int = MAX_BATCH_CHARS,
    max_batches: int = MAX_BATCHES,
    llm_timeout_seconds: float = LLM_CALL_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """对当前用户指定 PDF 做全文总结（短文一次，长文 Map-Reduce）。

    任一模型批次失败时抛出 SummarizeModelError，不返回伪完整终稿。
    """

    document = get_document_chunks(
        user_id=user_id,
        filename=filename,
        store=store,
    )
    chunks = document["chunks"]
    if not chunks:
        raise DocumentNotFoundError(
            f"文件「{document['filename']}」没有可用文本。"
        )

    non_empty = [c for c in chunks if (c.get("content") or "").strip()]
    if not non_empty:
        raise DocumentNotFoundError(
            f"文件「{document['filename']}」没有可用文本。"
        )

    batches = split_chunks_into_batches(
        non_empty,
        max_batch_chars=max_batch_chars,
    )
    if len(batches) > max_batches:
        raise DocumentTooLargeError(
            f"文件「{document['filename']}」过长，"
            f"需分成 {len(batches)} 批，超过上限 {max_batches} 批。"
            "请缩小文档或拆分后再试。"
        )

    model_fn = chat_fn or chat_with_ai
    source_name = document["filename"]

    if len(batches) == 1:
        summary = _oneshot_summary(
            filename=source_name,
            batch=batches[0],
            focus=focus,
            chat_fn=model_fn,
            timeout=llm_timeout_seconds,
        )
        mode = "oneshot"
        partial_count = 0
    else:
        partials: list[str] = []
        batch_count = len(batches)
        for index, batch in enumerate(batches, start=1):
            partial = _map_batch_summary(
                filename=source_name,
                batch_index=index,
                batch_count=batch_count,
                batch=batch,
                focus=focus,
                chat_fn=model_fn,
                timeout=llm_timeout_seconds,
            )
            partials.append(partial)

        summary = _reduce_summaries(
            filename=source_name,
            partials=partials,
            focus=focus,
            chat_fn=model_fn,
            timeout=llm_timeout_seconds,
        )
        mode = "map_reduce"
        partial_count = len(partials)

    return {
        "filename": source_name,
        "file_hash": document["file_hash"],
        "chunk_count": document["chunk_count"],
        "page_count": document["page_count"],
        "batch_count": len(batches),
        "mode": mode,
        "partial_count": partial_count,
        "summary": summary,
    }


# 供 API 层统一引用异常类型
__all__ = [
    "MAX_BATCH_CHARS",
    "MAX_BATCHES",
    "LLM_CALL_TIMEOUT_SECONDS",
    "DocumentTooLargeError",
    "SummarizeModelError",
    "DocumentNotFoundError",
    "DocumentVersionConflictError",
    "split_chunks_into_batches",
    "summarize_document",
]
