import math


def cosine_similarity(
    vector_a: list[float],
    vector_b: list[float],
) -> float:
    """
    计算两个向量之间的余弦相似度。

    Args:
        vector_a: 第一个向量
        vector_b: 第二个向量

    Returns:
        float: 两个向量之间的余弦相似度
    """

    # 两个向量必须拥有相同的维度
    if len(vector_a) != len(vector_b):
        raise ValueError("两个向量的维度必须一致")

    # 计算点积
    dot_product = sum(
        a * b
        for a, b in zip(vector_a, vector_b)
    )

    # 计算 vector_a 的长度
    magnitude_a = math.sqrt(
        sum(a * a for a in vector_a)
    )

    # 计算 vector_b 的长度
    magnitude_b = math.sqrt(
        sum(b * b for b in vector_b)
    )

    # 防止除以 0
    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0

    return dot_product / (magnitude_a * magnitude_b)