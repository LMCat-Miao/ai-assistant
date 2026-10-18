def split_text(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> list[str]:
    """
    将长文本切分成多个 Chunk。

    Args:
        text: 原始文本
        chunk_size: 每个 Chunk 的最大长度
        chunk_overlap: 相邻 Chunk 的重叠长度

    Returns:
        list[str]: Chunk 列表
    """

    if not text:
        return []

    if chunk_overlap >= chunk_size:
        raise ValueError(
            "chunk_overlap 必须小于 chunk_size"
        )

    chunks: list[str] = []

    start = 0
    text_length = len(text)

    while start < text_length:
        end = start + chunk_size

        chunk = text[start:end]

        if chunk:
            chunks.append(chunk)

        start = end - chunk_overlap

    return chunks