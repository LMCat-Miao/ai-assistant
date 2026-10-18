from sentence_transformers import SentenceTransformer
from app.rag.vector_store import VectorStore

#加载向量模型
model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
# 准备三条用于验证的知识文本。
documents = [
    "Vue 3 使用 Proxy 实现响应式系统，可以追踪对象属性的读取和修改。",
    "Vue 的 computed 用于缓存计算结果，当依赖的数据变化时会重新计算。",
    "Python 可以用于人工智能开发、数据分析和自然语言处理。",
]

ids = [
    "demo_vue_001",
    "demo_vue_002",
    "demo_python_001",
]

metadatas = [
    {"topic": "Vue", "source": "vector_store_test"},
    {"topic": "Vue", "source": "vector_store_test"},
    {"topic": "Python", "source": "vector_store_test"},
]
#只在写入阶段将文本转换成向量
document_embeddings = model.encode(documents).tolist()
#创建向量数据库封装对象
store = VectorStore()
#写入测试数据
store.add_chunks(
    ids=ids,
    documents=documents,
    embeddings=document_embeddings,
    metadatas=metadatas,
)
print("当前数据库记录数：", store.collection.count())

# 模拟用户提出的问题。
question = "Vue 3 的响应式原理是什么？"

# 将用户问题转换为向量。
question_embedding = model.encode(question).tolist()

# 检索最相关的两条文本。
results = store.search(
    query_embedding=question_embedding,
    top_k=2,
)

print("\n检索结果：")

for index, result in enumerate(results, start=1):
    print(f"\n第 {index} 条结果")
    print("ID：", result["id"])
    print("文本：", result["document"])
    print("元数据：", result["metadata"])
    print("距离：", round(result["distance"], 4))

# 只检索 Vue 类别的数据。
vue_results = store.search(
    query_embedding=question_embedding,
    top_k=2,
    where={"topic": "Vue"},
)

print("\n只检索 Vue 类别：")

for result in vue_results:
    print(result["document"])