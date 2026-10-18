
from sentence_transformers import SentenceTransformer

from app.rag.vector_store import VectorStore


MODEL_NAME = "BAAI/bge-small-zh-v1.5"


def main():
    # 输入一个与你上传的 resume.pdf 内容相关的问题。
    query = input("请输入检索问题：").strip()

    if not query:
        print("问题不能为空。")
        return

    # 加载与入库阶段相同的 Embedding 模型。
    model = SentenceTransformer(MODEL_NAME)

    # 将问题转换成向量。
    query_embedding = model.encode(
        query,
        normalize_embeddings=True,
    ).tolist()

    # 初始化向量数据库。
    store = VectorStore()

    # 仅查询当前测试用户的数据。
    # 请将下面的值替换为你登录账号在 JWT 中对应的 sub。
    user_id = input("请输入当前测试账号的 user_id：").strip()

    if not user_id:
        print("user_id 不能为空。")
        return

    results = store.search(
        query_embedding=query_embedding,
        top_k=3,
        where={"user_id": user_id},
    )

    if not results:
        print("没有找到匹配的文本块。")
        return

    for index, item in enumerate(results, start=1):
        print(f"\n--- 检索结果 {index} ---")
        print("相似度距离：", item["distance"])
        print("来源：", item["metadata"].get("source"))
        print("页码：", item["metadata"].get("page"))
        print("文本：", item["document"])


if __name__ == "__main__":
    main()
