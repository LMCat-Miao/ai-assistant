
"""
RAG 检索效果检查脚本

用途：
1. 查询当前用户的知识库。
2. 打印每条结果的文本、来源、页码和距离。
3. 检查返回结果是否与问题相关。

注意：
- 使用你已经存在的用户 ID 和 PDF 文件名。
- 本脚本只读取检索结果，不会修改数据库。
"""

from pprint import pprint

from app.services.rag_retrieval_service import retrieve_knowledge


def main() -> None:
    # 修改为你当前测试账号对应的 user_id。
    user_id = "1"

    # 修改为你已经上传的 PDF 文件名。
    filename = "resume.pdf"

    # 设计一个与你上传资料有关的真实问题。
    query = "总结这份 PDF 的核心内容"

    results = retrieve_knowledge(
        query=query,
        user_id=user_id,
        top_k=3,
        filename=filename,
    )

    print("\n" + "=" * 60)
    print(f"用户问题：{query}")
    print(f"检索结果数量：{len(results)}")
    print("=" * 60)

    if not results:
        print("没有检索到结果，请检查用户 ID、文件名和知识库数据。")
        return

    for index, item in enumerate(results, start=1):
        print(f"\n第 {index} 条检索结果")
        print("-" * 40)
        print(f"来源：{item['source']}")
        print(f"页码：{item['page']}")
        print(f"距离：{item['distance']}")
        print(f"文本：{item['content']}")

    print("\n检索结果原始结构：")
    pprint(results)


if __name__ == "__main__":
    main()
