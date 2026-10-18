def fake_embedding(text: str) -> list[float]:
    """
    模拟 Embedding 模型。

    实际项目中，这里应该调用真正的 Embedding 模型。
    目前只是为了理解：
    
    文本
      ↓
    Embedding
      ↓
    向量
    """

    return [
        0.12,
        -0.38,
        0.72,
        0.15,
        -0.21,
    ]