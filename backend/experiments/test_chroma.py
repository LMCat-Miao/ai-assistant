
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer


# 第一步：定义 Chroma 数据库的本地存储目录
# 数据保存在项目 backend/data/chroma_db 中
BASE_DIR = Path(__file__).resolve().parents[1]
CHROMA_DIR = BASE_DIR / "data" / "chroma_db"


# 第二步：创建持久化数据库客户端
# 如果目录不存在，Chroma 会创建所需的存储结构
client = chromadb.PersistentClient(
    path=str(CHROMA_DIR)
)


# 第三步：创建或获取一个 Collection
# get_or_create_collection 可以避免重复运行时因集合已存在而报错
collection = client.get_or_create_collection(
    name="ai_learning_knowledge",
    metadata={"description": "AI 学习助手知识库实验"},
)


# 第四步：加载之前使用的中文 Embedding 模型
model = SentenceTransformer("BAAI/bge-small-zh-v1.5")


# 第五步：准备三个知识库 Chunk
chunks = [
    "Vue 3 使用 Proxy 实现响应式系统，可以追踪对象属性的读取和修改。",
    "Vue 的 computed 用于缓存计算结果，当依赖的数据变化时会重新计算。",
    "Python 可以用于人工智能开发，常见的应用包括机器学习、数据分析和自然语言处理。",
]


# 第六步：给每个 Chunk 生成唯一 ID
ids = [
    "vue_chunk_001",
    "vue_chunk_002",
    "python_chunk_001",
]


# 第七步：为三个 Chunk 生成真实向量
# encode() 返回 NumPy 数组，tolist() 转成普通 Python 列表
embeddings = model.encode(chunks).tolist()


# 第八步：保存文本、向量和元数据
# upsert 表示有相同 ID 时更新，没有时新增
collection.upsert(
    ids=ids,
    documents=chunks,
    embeddings=embeddings,
    metadatas=[
        {"topic": "Vue", "source": "demo"},
        {"topic": "Vue", "source": "demo"},
        {"topic": "Python", "source": "demo"},
    ],
)


# 第九步：查看数据库中有多少条记录
print("Chroma 数据库目录：", CHROMA_DIR)
print("当前 Collection：", collection.name)
print("知识库记录数：", collection.count())


# 第十步：读取并展示已保存的记录
stored_data = collection.get(
    include=["documents", "metadatas"]
)

print("\n数据库中保存的内容：")

for record_id, document, metadata in zip(
    stored_data["ids"],
    stored_data["documents"],
    stored_data["metadatas"],
):
    print(f"\nID：{record_id}")
    print(f"文本：{document}")
    print(f"元数据：{metadata}")


# 第十一步：模拟用户提出的问题
query = "Vue 3 的响应式原理是什么？"

# 第十二步：使用相同的 BGE 模型生成查询向量
query_vector = model.encode(query).tolist()

# 第十三步：让 Chroma 从已保存的知识中检索最相关的 2 条
results = collection.query(
    query_embeddings=[query_vector],
    n_results=2,
    include=[
        "documents",
        "metadatas",
        "distances",
    ],
)

# 第十四步：打印检索结果
print("\n========== 向量检索结果 ==========")
print(f"用户问题：{query}")

# query() 的结果按查询问题分组
# 即使只查询一个问题，返回的 documents 也是二维列表
documents = results["documents"][0]
metadatas = results["metadatas"][0]
distances = results["distances"][0]
ids = results["ids"][0]

for index, (record_id, document, metadata, distance) in enumerate(
    zip(ids, documents, metadatas, distances),
    start=1,
):
    print(f"\n第 {index} 条结果")
    print(f"ID：{record_id}")
    print(f"文本：{document}")
    print(f"元数据：{metadata}")
    print(f"距离：{distance:.4f}")