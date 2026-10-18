
from sentence_transformers import SentenceTransformer

from app.rag.vector_store import VectorStore


MODEL_NAME = "BAAI/bge-small-zh-v1.5"


def main() -> None:
    # 加载与入库时相同的向量模型。
    model = SentenceTransformer(
    MODEL_NAME,
    local_files_only=True,
)

    store = VectorStore()

    # 在这里输入一个确实出现在 PDF 中的问题。
    question = "专业技能都有什么"

    # 将问题转换成向量。
    query_embedding = model.encode(
        question,
        normalize_embeddings=True,
    ).tolist()

    # 执行 Top-K 检索。
    results = store.search(
        query_embedding=query_embedding,
        top_k=3,
        where={"file_type": "pdf"},
    )

    print(f"问题：{question}")

    if not results:
        print("没有检索到结果，请检查是否已完成 PDF 入库。")
        return

    for index, result in enumerate(results, start=1):
        metadata = result["metadata"]

        print(f"\n--- 第 {index} 条结果 ---")
        print("来源：", metadata.get("source"))
        print("页码：", metadata.get("page"))
        print("距离：", round(result["distance"], 4))
        print("文本：", result["document"])


if __name__ == "__main__":
    main()