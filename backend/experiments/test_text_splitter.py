
from app.rag.text_splitter import spilt_text


def main() -> None:
    text = (
        "第一段：RAG 是检索增强生成技术。"
        "它可以先从知识库中查找相关资料。"
        "然后把资料提供给大模型。"
        "大模型根据资料和用户问题生成回答。"
        "第二段：Embedding 用于把文本转换成向量。"
        "Chroma 可以存储向量并进行相似度检索。"
    )

    chunk_size = 50
    chunk_overlap = 10

    chunks = spilt_text(
        text,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    print(f"原文长度：{len(text)}")
    print(f"分块数量：{len(chunks)}")

    for index, chunk in enumerate(chunks, start=1):
        print("\n" + "=" * 40)
        print(f"Chunk {index}")
        print(f"字符长度：{len(chunk)}")
        print(f"文本内容：{chunk}")

    # 测试 1：空文本应返回空列表。
    assert spilt_text("   ") == []

    # 测试 2：非法参数应抛出异常。
    try:
        spilt_text("测试文本", chunk_size=10, chunk_overlap=10)
    except ValueError:
        print("\n参数校验测试通过")
    else:
        raise AssertionError("非法参数没有触发 ValueError")

    # 测试 3：每个文本块都不能超过当前版本允许的最大长度。
    # 当前版本允许 overlap 叠加到正文，因此这里使用宽松上限。
    max_allowed_length = chunk_size + chunk_overlap
    assert all(len(chunk) <= max_allowed_length for chunk in chunks)

    # 测试 4：原文中的关键内容必须出现在结果中。
    combined = "".join(chunks)
    assert "相似度检索。" in combined
    assert "大模型根据资料和用户问题生成回答。" in combined

    print("\n基础测试全部通过")


if __name__ == "__main__":
    main()
