"""RAG 文档入库服务：PDF 解析、文本切分、向量化和向量存储。"""

import hashlib
import logging
from pathlib import Path
from typing import Any

from sentence_transformers import SentenceTransformer

from app.rag.pdf_loader import extract_pdf_pages
from app.rag.text_splitter import spilt_text
from app.rag.vector_store import VectorStore


logger = logging.getLogger(__name__)

# 与已验证的实验代码使用相同的 Embedding 模型。
MODEL_NAME = "BAAI/bge-small-zh-v1.5"

# 模型只在首次需要时加载，避免每次上传都重新初始化。
_embedding_model: SentenceTransformer | None = None


def get_embedding_model() -> SentenceTransformer:
    """获取共享的文本向量模型。"""
    global _embedding_model

    if _embedding_model is None:
        _embedding_model = SentenceTransformer(MODEL_NAME)

    return _embedding_model


def build_user_source_where(user_id: str, source: str) -> dict[str, Any]:
    """构造仅限定当前用户 + 目标文件名的 Chroma metadata 过滤条件。"""

    return {
        "$and": [
            {"user_id": str(user_id)},
            {"source": source},
        ]
    }


def remove_stale_chunks_for_document(
    store: VectorStore,
    user_id: str,
    source: str,
    keep_file_hash: str,
) -> int:
    """删除同一用户、同一文件名下不属于当前 file_hash 的旧 Chunk。

    只按 user_id + source 查询，再按 ID 精确删除，避免误删其他用户或其他文件。
    无 file_hash 的历史数据也会被当作旧版本清理。
    """

    result = store.get_chunks(
        where=build_user_source_where(user_id, source),
        include=["metadatas"],
    )

    stale_ids: list[str] = []
    for record_id, metadata in zip(result["ids"], result["metadatas"]):
        meta = metadata or {}
        if meta.get("file_hash") != keep_file_hash:
            stale_ids.append(record_id)

    return store.delete_by_ids(stale_ids)


def ingest_pdf(
    pdf_path: str | Path,
    user_id: str,
    original_filename: str,
    store: VectorStore | None = None,
) -> dict[str, Any]:
    """处理 PDF，并将带有用户归属信息的文本块写入 Chroma。

    同名文件更新策略（失败安全）：
    1. 先完成解析、向量化并 upsert 新版本；
    2. 仅在新版本写入成功后，再清理同一用户、同一文件名的旧版本 Chunk；
    3. 若写入失败，旧版本保持可用；若清理失败，新旧可能短暂并存，
       上传仍视为成功，并在返回值中标记清理状态。
    """

    file_path = Path(pdf_path)
    source_name = Path(original_filename).name

    # 1. 读取 PDF，提取每一页的文本。
    pages = extract_pdf_pages(file_path)

    # 2. 按页切分文本，同时保存页码等元数据。
    # 3. 计算文件哈希，用于生成稳定的文件标识，并写入 metadata 便于清理旧版。
    file_hash = hashlib.sha256(
        file_path.read_bytes()
    ).hexdigest()[:16]

    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []
    chunk_index = 0

    for page_data in pages:
        chunks = spilt_text(
            page_data["text"],
            chunk_size=500,
            chunk_overlap=80,
        )

        for chunk in chunks:
            documents.append(chunk)
            metadatas.append({
                "user_id": str(user_id),
                "source": source_name,
                "page": int(page_data["page"]),
                "file_type": "pdf",
                "file_hash": file_hash,
                # 全局顺序，便于全文总结时稳定排序（不依赖 Chroma 返回顺序）。
                "chunk_index": int(chunk_index),
            })
            chunk_index += 1

    if not documents:
        raise ValueError("PDF 中没有可入库的文本。")

    # Chroma 的 ID 必须在整个 Collection 内唯一。
    # 将用户标识加入 ID，避免不同用户的相同 PDF 相互覆盖。
    user_hash = hashlib.sha256(
        str(user_id).encode("utf-8")
    ).hexdigest()[:12]

    ids = [
        f"pdf_{user_hash}_{file_hash}_chunk_{index:04d}"
        for index in range(len(documents))
    ]

    # 4. 使用真正的 BGE 模型生成向量。
    model = get_embedding_model()

    embeddings = model.encode(
        documents,
        show_progress_bar=False,
        normalize_embeddings=True,
    ).tolist()

    # 5. 复用现有 VectorStore，将数据写入 Chroma。
    #    关键：先 upsert 新版本，绝不在写入成功前删除旧数据。
    vector_store = store if store is not None else VectorStore()

    vector_store.add_chunks(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )

    # 6. 新版本已成功入库后，再清理同用户同文件名的旧 Chunk。
    removed_old_chunks = 0
    stale_cleanup_ok = True
    stale_cleanup_error: str | None = None

    try:
        removed_old_chunks = remove_stale_chunks_for_document(
            store=vector_store,
            user_id=str(user_id),
            source=source_name,
            keep_file_hash=file_hash,
        )
    except Exception as exc:
        # 清理失败不应回滚已成功写入的新版本，也不应让用户感知为整次上传失败。
        stale_cleanup_ok = False
        stale_cleanup_error = str(exc)
        logger.warning(
            "新版本已入库，但清理旧 Chunk 失败 user_id=%s source=%s: %s",
            user_id,
            source_name,
            exc,
        )

    return {
        "filename": source_name,
        "file_hash": file_hash,
        "pages": len(pages),
        "chunks": len(documents),
        "removed_old_chunks": removed_old_chunks,
        "stale_cleanup_ok": stale_cleanup_ok,
        "stale_cleanup_error": stale_cleanup_error,
    }
