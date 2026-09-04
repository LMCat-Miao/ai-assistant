from pathlib import Path
import sys
import transformers

#获取backend目录的绝对路径
BASE_DIR = Path(__file__).resolve().parent.parent

#deepseek官方所在的路径
TOKENIZER_DIR =(
    BASE_DIR
    /"tokenizer"
    /"deepseek_v4_tokenizer"
)
print("TOKENIZER_DIR:")
print(TOKENIZER_DIR)

tokenizer = transformers.AutoTokenizer.from_pretrained(
    TOKENIZER_DIR, trust_remote_code=True
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
result = tokenizer.encode(texts)

print("文本：", texts)
print("Token IDs：", result)
print("Token 数量：", len(result))