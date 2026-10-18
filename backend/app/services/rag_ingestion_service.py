
"""RAG 文档入库服务：PDF 解析、文本切分、向量化和向量存储。"""

import hashlib
from pathlib import Path
from typing import Any

from sentence_transformers import SentenceTransformer

from app.rag.pdf_loader import extract_pdf_pages
from app.rag.text_splitter import spilt_text
from app.rag.vector_store import VectorStore


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


def ingest_pdf(
    pdf_path: str | Path,
    user_id: str,
    original_filename: str,
) -> dict[str, Any]:
    """处理 PDF，并将带有用户归属信息的文本块写入 Chroma。"""

    file_path = Path(pdf_path)

    # 1. 读取 PDF，提取每一页的文本。
    pages = extract_pdf_pages(file_path)

    # 2. 按页切分文本，同时保存页码等元数据。
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []

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
                "source": Path(original_filename).name,
                "page": int(page_data["page"]),
                "file_type": "pdf",
            })

    if not documents:
        raise ValueError("PDF 中没有可入库的文本。")

    # 3. 计算文件哈希，用于生成稳定的文件标识。
    file_hash = hashlib.sha256(
        file_path.read_bytes()
    ).hexdigest()[:16]

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
    store = VectorStore()

    store.add_chunks(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )

    return {
        "filename": Path(original_filename).name,
        "file_hash": file_hash,
        "pages": len(pages),
        "chunks": len(documents),
    }
