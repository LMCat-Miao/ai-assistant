
"""RAG 检索服务：将用户问题向量化，并从知识库召回相关文本。"""

from typing import Any

from app.rag.vector_store import VectorStore
from app.services.rag_ingestion_service import get_embedding_model


def retrieve_knowledge(
    query: str,
    user_id: str,
    top_k: int = 3,
    filename: str | None = None,
) -> list[dict[str, Any]]:
    """
    根据用户问题检索相关知识。

    Args:
        query: 用户提出的问题。
        user_id: 当前登录用户的 ID。
        top_k: 最多返回多少个文本块。
        filename: 可选，指定只检索某个 PDF。

    Returns:
        包含文本内容、来源、页码和距离的检索结果列表。
    """
    query = query.strip()

    if not query:
        raise ValueError("检索问题不能为空。")

    if not user_id:
        raise ValueError("用户 ID 不能为空。")

    if not 1 <= top_k <= 10:
        raise ValueError("top_k 必须在 1 到 10 之间。")

    # 使用与入库阶段相同的 BGE 模型，将问题转换成向量。
    model = get_embedding_model()
    query_embedding = model.encode(
        query,
        normalize_embeddings=True,
        show_progress_bar=False,
    ).tolist()

    # 默认只检索当前用户自己的知识库。
    where: dict[str, Any] = {"user_id": str(user_id)}

    # 如果指定文件名，则进一步缩小检索范围。
    if filename:
        where = {
            "$and": [
                {"user_id": {"$eq": str(user_id)}},
                {"source": {"$eq": filename}},
            ]
        }

    store = VectorStore()

    results = store.search(
        query_embedding=query_embedding,
        top_k=top_k,
        where=where,
    )

    # 将向量数据库结果整理成适合 API 返回的数据。
    return [
        {
            "content": item["document"],
            "source": item["metadata"].get("source"),
            "page": item["metadata"].get("page"),
            "distance": item["distance"],
        }
        for item in results
    ]
