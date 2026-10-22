from pathlib import Path
from typing import Any

import chromadb


# 获取 backend 项目的根目录。
# 当前文件位于 backend/app/rag/vector_store.py，
# parents[2] 对应 backend 目录。
BASE_DIR = Path(__file__).resolve().parents[2]

# Chroma 使用本地持久化目录，程序重启后数据仍然保留。
CHROMA_DIR = BASE_DIR / "data" / "chroma_db"

# 与之前的实验保持相同的 Collection 名称，
# 这样可以继续访问之前保存的实验数据。
COLLECTION_NAME = "ai_learning_knowledge"


class VectorStore:
    """封装 Chroma 向量数据库的存储与检索操作。"""

    def __init__(
        self,
        persist_directory: str | Path | None = None,
        collection_name: str | None = None,
    ) -> None:
        # 允许测试注入临时目录 / 独立 collection，避免污染真实用户数据。
        chroma_dir = Path(persist_directory) if persist_directory else CHROMA_DIR
        name = collection_name or COLLECTION_NAME

        # 创建数据库目录，目录已存在时不会报错。
        chroma_dir.mkdir(parents=True, exist_ok=True)

        # 创建连接本地持久化数据库的客户端。
        self.client = chromadb.PersistentClient(
            path=str(chroma_dir)
        )

        # 获取已有集合；不存在时才创建。
        self.collection = self.client.get_or_create_collection(
            name=name,
            metadata={"description": "AI 学习助手知识库"},
        )

    def add_chunks(
        self,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """将文本分块、对应向量和元数据写入数据库。"""

        # 检查每条数据是否一一对应，避免错误关联。
        if not (
            len(ids)
            == len(documents)
            == len(embeddings)
            == len(metadatas)
        ):
            raise ValueError("ID、文本、向量和元数据数量必须一致")

        if not ids:
            return

        # upsert 表示：ID 不存在则新增，已存在则更新。
        self.collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def get_chunks(
        self,
        where: dict[str, Any] | None = None,
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        """按元数据条件读取记录，供清理旧版本等业务使用。"""

        options: dict[str, Any] = {
            "include": include or ["metadatas", "documents"],
        }
        if where is not None:
            options["where"] = where

        result = self.collection.get(**options)
        return {
            "ids": list(result.get("ids") or []),
            "documents": list(result.get("documents") or []),
            "metadatas": list(result.get("metadatas") or []),
        }

    def delete_by_ids(self, ids: list[str]) -> int:
        """仅按明确的 ID 列表删除，避免宽泛 where 误删。"""

        if not ids:
            return 0

        self.collection.delete(ids=ids)
        return len(ids)

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 3,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """根据问题向量检索最相关的文本块。"""

        if top_k < 1:
            raise ValueError("top_k 必须大于等于 1")

        # 空集合不需要执行检索。
        if self.collection.count() == 0:
            return []

        # 实际返回数量不能超过集合内的记录数。
        result_count = min(top_k, self.collection.count())

        query_options: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": result_count,
            "include": [
                "documents",
                "metadatas",
                "distances",
            ],
        }

        # where 用于筛选指定类别、文档或其他元数据。
        if where is not None:
            query_options["where"] = where

        results = self.collection.query(**query_options)

        # Chroma 的结果按查询语句分组。
        # 本次只有一个问题，因此读取索引 0。
        ids = results["ids"][0]
        documents = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results["distances"][0]

        # 整理为业务代码更容易使用的数据结构。
        return [
            {
                "id": record_id,
                "document": document,
                "metadata": metadata,
                "distance": distance,
            }
            for record_id, document, metadata, distance
            in zip(ids, documents, metadatas, distances)
        ]
