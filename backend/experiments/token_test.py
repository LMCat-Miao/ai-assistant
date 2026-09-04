from transformers import AutoTokenizer


# 加载 Tokenizer
tokenizer = AutoTokenizer.from_pretrained(
    "deepseek-ai/DeepSeek-V3"
)


texts = [
    # 中文
    "你好",
    "人工智能正在改变软件开发的方式。",

    # 英文
    "Hello",
    "Hello, I am learning Vue.",

    # 代码
    "const messages = []",
    "const user = { name: 'admin' }",

    # 中英文混合
    "我正在学习 Vue3。",
    "我正在学习 Vue3 + TypeScript。",

    # 更长的自然语言
    "我正在开发一个 AI 学习助手，它支持智能聊天、PDF 解析和 RAG 知识库。",
]


for text in texts:
    print("=" * 60)

    # 原始文本
    print("文本：", text)

    # 字符数量
    char_count = len(text)

    # Token ID
    token_ids = tokenizer.encode(
        text,
        add_special_tokens=False
    )

    # Token 数量
    token_count = len(token_ids)

    # Token
    tokens = tokenizer.convert_ids_to_tokens(token_ids)

    print("字符数：", char_count)
    print("Token数：", token_count)
    print("Token IDs：", token_ids)
    print("Tokens：", tokens)