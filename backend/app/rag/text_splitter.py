
import re


def spilt_text(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 80,
) -> list[str]:
    """优先按句子边界切分文本，并添加相邻块重叠内容。"""

    if chunk_size <= 0:
        raise ValueError("chunk_size 必须大于 0")

    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError(
            "chunk_overlap 必须大于等于 0 且小于 chunk_size"
        )

    text = text.strip()
    if not text:
        return []

    # 先按空行拆分段落，再按句末标点拆分句子。
    paragraphs = re.split(r"\n\s*\n", text)
    units: list[str] = []

    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue

        sentences = re.split(r"(?<=[。！？!?；;])", paragraph)

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # 超长句子无法完整放入单个块，只能按长度切分。
            start = 0
            while start < len(sentence):
                end = min(start + chunk_size, len(sentence))
                units.append(sentence[start:end])

                if end == len(sentence):
                    break

                start = end

    # 第一步：生成正文块，保证正文顺序和内容不丢失。
    base_chunks: list[str] = []
    current = ""

    for unit in units:
        candidate = current + unit

        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current:
                base_chunks.append(current)
            current = unit

    if current:
        base_chunks.append(current)

    # 第二步：给后续块添加前一块的尾部作为上下文。
    # 正文块不做截断，因此添加重叠后可能略长于 chunk_size。
    if chunk_overlap == 0 or len(base_chunks) <= 1:
        return base_chunks

    result = [base_chunks[0]]

    for index in range(1, len(base_chunks)):
        previous = base_chunks[index - 1]
        current = base_chunks[index]

        overlap = previous[-chunk_overlap:]
        result.append(overlap + current)

    return result
