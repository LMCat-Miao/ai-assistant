"""按用户与文件名读取知识库全文 Chunk，供文档列表与全文总结使用。"""

from __future__ import annotations

import re
from typing import Any

from app.rag.vector_store import VectorStore
from app.services.rag_ingestion_service import build_user_source_where


# 与入库 ID 约定一致：pdf_{user_hash12}_{file_hash16}_chunk_{index}
_CHUNK_ID_PATTERN = re.compile(
    r"^pdf_([0-9a-f]{12})_([0-9a-f]{16})_chunk_(\d+)$",
    re.IGNORECASE,
)


class DocumentNotFoundError(Exception):
    """当前用户下找不到指定文件名的知识库文档。"""


class DocumentVersionConflictError(Exception):
    """同一用户同一文件名存在多个无法可靠判定的版本。"""


def parse_chunk_index_from_id(record_id: str) -> int | None:
    """从 Chunk ID 后缀解析全局序号；无法解析时返回 None。"""

    match = _CHUNK_ID_PATTERN.match(record_id or "")
    if not match:
        return None
    return int(match.group(3))


def parse_file_hash_from_id(record_id: str) -> str | None:
    """从 Chunk ID 中解析 file_hash；无法解析时返回 None。"""

    match = _CHUNK_ID_PATTERN.match(record_id or "")
    if not match:
        return None
    return match.group(2).lower()


def resolve_chunk_index(record_id: str, metadata: dict[str, Any] | None) -> int:
    """优先使用 metadata.chunk_index，否则回退解析 ID 后缀。"""

    meta = metadata or {}
    raw = meta.get("chunk_index")
    if raw is not None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            pass

    parsed = parse_chunk_index_from_id(record_id)
    if parsed is not None:
        return parsed

    # 无法得到稳定顺序时放到末尾，并依赖 page 作为次级键。
    return 10**9


def resolve_effective_file_hash(
    record_id: str,
    metadata: dict[str, Any] | None,
) -> str | None:
    """得到该 Chunk 的有效版本哈希：metadata 优先，其次 ID。"""

    meta = metadata or {}
    raw = meta.get("file_hash")
    if isinstance(raw, str) and raw.strip():
        return raw.strip().lower()

    return parse_file_hash_from_id(record_id)


def _validate_single_version(
    rows: list[dict[str, Any]],
    filename: str,
) -> str | None:
    """校验 rows 是否属于同一可靠版本，返回统一 file_hash（legacy 可为 None）。"""

    hashes: set[str] = set()
    missing = 0

    for row in rows:
        effective = row.get("effective_file_hash")
        if effective is None:
            missing += 1
        else:
            hashes.add(effective)

    # 新旧混杂：部分有 hash、部分完全无法识别。
    if missing and hashes:
        raise DocumentVersionConflictError(
            f"文件「{filename}」同时存在带版本标识与无法识别版本的记录，"
            "无法可靠判断应总结哪一版。请重新上传该 PDF 以清理旧数据。"
        )

    if len(hashes) > 1:
        raise DocumentVersionConflictError(
            f"文件「{filename}」在知识库中存在多个内容版本（file_hash 不一致），"
            "无法可靠判断当前版本。请重新上传该 PDF。"
        )

    if missing and not hashes:
        # 全部无法解析版本：不能冒充“唯一当前版”。
        raise DocumentVersionConflictError(
            f"文件「{filename}」的历史记录缺少可解析的版本标识，"
            "无法可靠定位文档版本。请重新上传该 PDF。"
        )

    return next(iter(hashes)) if hashes else None


def get_document_chunks(
    user_id: str,
    filename: str,
    store: VectorStore | None = None,
) -> dict[str, Any]:
    """读取当前用户指定 PDF 的全部 Chunk，并按文档顺序排序。

    过滤条件严格限定为 JWT 用户 user_id + 文件名 source。
    多版本或新旧混杂时抛出 DocumentVersionConflictError，不猜测最新版。
    """

    if not user_id:
        raise ValueError("用户 ID 不能为空。")

    source = (filename or "").strip()
    if not source:
        raise ValueError("文件名不能为空。")

    # 只使用 basename，避免路径穿越式文件名干扰过滤。
    source = source.replace("\\", "/").split("/")[-1]

    vector_store = store if store is not None else VectorStore()
    raw = vector_store.get_chunks(
        where=build_user_source_where(str(user_id), source),
        include=["metadatas", "documents"],
    )

    if not raw["ids"]:
        raise DocumentNotFoundError(
            f"未找到文件「{source}」。请确认已上传到当前账号的知识库。"
        )

    rows: list[dict[str, Any]] = []
    for record_id, document, metadata in zip(
        raw["ids"],
        raw["documents"],
        raw["metadatas"],
    ):
        meta = metadata or {}
        # 双重校验：即使 where 异常，也不混入其他用户/文件。
        if str(meta.get("user_id")) != str(user_id):
            continue
        if str(meta.get("source") or "") != source:
            continue

        rows.append(
            {
                "id": record_id,
                "content": document or "",
                "page": meta.get("page"),
                "chunk_index": resolve_chunk_index(record_id, meta),
                "source": source,
                "file_hash": meta.get("file_hash"),
                "effective_file_hash": resolve_effective_file_hash(
                    record_id,
                    meta,
                ),
            }
        )

    if not rows:
        raise DocumentNotFoundError(
            f"未找到文件「{source}」。请确认已上传到当前账号的知识库。"
        )

    file_hash = _validate_single_version(rows, source)

    rows.sort(
        key=lambda item: (
            int(item["chunk_index"]),
            int(item["page"]) if item["page"] is not None else 10**9,
            item["id"],
        )
    )

    pages = {
        int(item["page"])
        for item in rows
        if item["page"] is not None
    }

    return {
        "filename": source,
        "file_hash": file_hash,
        "chunk_count": len(rows),
        "page_count": len(pages),
        "chunks": [
            {
                "id": item["id"],
                "content": item["content"],
                "page": item["page"],
                "chunk_index": item["chunk_index"],
                "source": item["source"],
                "file_hash": file_hash,
            }
            for item in rows
        ],
    }


def list_user_documents(
    user_id: str,
    store: VectorStore | None = None,
) -> list[dict[str, Any]]:
    """列出当前用户知识库中的文档（按文件名聚合）。"""

    if not user_id:
        raise ValueError("用户 ID 不能为空。")

    vector_store = store if store is not None else VectorStore()
    raw = vector_store.get_chunks(
        where={"user_id": str(user_id)},
        include=["metadatas"],
    )

    by_source: dict[str, list[dict[str, Any]]] = {}
    for record_id, metadata in zip(raw["ids"], raw["metadatas"]):
        meta = metadata or {}
        if str(meta.get("user_id")) != str(user_id):
            continue
        source = str(meta.get("source") or "").strip()
        if not source:
            continue
        by_source.setdefault(source, []).append(
            {
                "id": record_id,
                "page": meta.get("page"),
                "effective_file_hash": resolve_effective_file_hash(
                    record_id,
                    meta,
                ),
            }
        )

    documents: list[dict[str, Any]] = []
    for source in sorted(by_source.keys()):
        rows = by_source[source]
        version_conflict = False
        file_hash: str | None = None
        try:
            file_hash = _validate_single_version(rows, source)
        except DocumentVersionConflictError:
            version_conflict = True

        pages = {
            int(item["page"])
            for item in rows
            if item["page"] is not None
        }

        documents.append(
            {
                "filename": source,
                "chunk_count": len(rows),
                "page_count": len(pages),
                "file_hash": file_hash,
                "version_conflict": version_conflict,
            }
        )

    return documents
