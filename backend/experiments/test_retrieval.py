
from sentence_transformers import SentenceTransformer

from app.rag.similarity import cosine_similarity


# 第一步：加载真实的中文 Embedding 模型
# 这里与之前测试使用相同的模型
model = SentenceTransformer("BAAI/bge-small-zh-v1.5")


# 模拟知识库中的三个 Chunk
chunks = [
    "Vue 3 使用 Proxy 实现响应式系统，可以追踪对象属性的读取和修改。",
    "Vue 的 computed 用于缓存计算结果，当依赖的数据变化时会重新计算。",
    "Python 可以用于人工智能开发，常见的应用包括机器学习、数据分析和自然语言处理。",
]

#top-k函数
def retrieve_top_k(
    query: str,
    chunks: list[str],
    k: int = 2,
) -> list[dict]:
    """
    从知识库中检索与用户问题最相关的 Top-K 个 Chunk。

    Args:
        query: 用户的问题
        chunks: 知识库文本列表
        k: 返回的相关文本数量

    Returns:
        按相似度从高到低排列的检索结果
    """

    if k <= 0:
        return []

    # 将用户问题转换为向量
    query_vector = model.encode(query).tolist()

    # 批量将知识库文本转换为向量
    chunk_vectors = model.encode(chunks)

    results = []

    for chunk, vector in zip(chunks, chunk_vectors):
        score = cosine_similarity(
            query_vector,
            vector.tolist(),
        )

        results.append({
            "text": chunk,
            "score": score,
        })

    # 最相关的排在前面
    results.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    # 只返回前 K 条
    return results[:k]


# 测试：只取最相关的两个 Chunk
top_results = retrieve_top_k(
    query="Vue 3 的响应式原理是什么？",
    chunks=chunks,
    k=2,
)

print("\nTop-K 检索结果：")

for item in top_results:
    print(f"{item['score']:.4f} | {item['text']}")